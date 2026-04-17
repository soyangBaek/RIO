"""실제 mic → Silero VAD → Whisper 파이프라인을 백그라운드 스레드로 돌리고,
완성된 utterance 를 기존 AudioCapture 의 feed() 로 주입하는 어댑터.

설계:
  - sounddevice 콜백 스레드가 오디오 청크를 audio_queue 에 push
  - VAD 스레드가 audio_queue 를 빼내 Silero VAD 로 utterance 경계 판정
  - ASR 스레드가 utterance 를 꺼내 faster-whisper 로 전사
  - 전사 결과를 AudioCapture.feed() 로 밀어넣음 (기존 AudioWorker 가 tick 마다 꺼내서 소비)

Frame 주입 프로토콜 (utterance 1건 당):
  1. {"speech": True}                             → 스텁 VAD 가 STARTED 이벤트 발행
  2. {"speech": True, "transcript": ..., ...}     → 스텁 STT 가 Transcript 반환
                                                    → IntentNormalizer 가 voice.intent.* 발행
  3. {"speech": False} × silence_frames_to_end    → 스텁 VAD 가 ENDED 이벤트 발행

Depth=1 동시성 규칙:
  - ASR 처리 중이거나 이미 대기 utterance 가 있으면 새 발화는 즉시 drop
  - 응답 일관성 + Pi CPU 보호 목적

Context manager 프로토콜:
  - `with LiveVoiceBackend(...) as backend:` 로 써서 start/stop 순서 실수 방지
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from src.app.adapters.audio.capture import AudioCapture
from src.app.adapters.audio.mic_gain import apply_mic_gain


_LOGGER = logging.getLogger(__name__)

# Silero ONNX 는 16kHz 에서 정확히 512 샘플 청크를 요구.
_EXPECTED_CHUNK = 512


@dataclass
class AudioParams:
    device: Optional[str] = "pulse"
    sample_rate: int = 16000
    channels: int = 1
    blocksize: int = 512
    dtype: str = "float32"
    mic_gain_percent: Optional[int] = 25
    gain_target_source: Optional[str] = None


@dataclass
class VADParams:
    threshold: float = 0.85
    min_silence_duration_ms: int = 300
    speech_pad_ms: int = 30
    min_speech_ms: int = 150
    sample_rate: int = 16000


@dataclass
class ASRParams:
    model: str = "base"
    language: str = "ko"
    beam_size: int = 1
    compute_type: str = "int8"
    device: str = "cpu"
    no_speech_threshold: float = 0.6
    condition_on_previous_text: bool = True
    min_logprob: float = -1.0


@dataclass
class BackendConfig:
    audio: AudioParams
    vad: VADParams
    asr: ASRParams
    drop_while_busy: bool = True
    silence_frames_to_feed: int = 2  # 스텁 VAD 의 silence_frames_to_end 기본값과 맞춤


# ── 내부 유틸: 롤링 버퍼 (absolute sample index) ─────────────
class _AudioBuffer:
    def __init__(self, max_seconds: float, sample_rate: int):
        self.max_samples = int(max_seconds * sample_rate)
        self.samples = np.zeros(0, dtype=np.float32)
        self.start_idx = 0

    def push(self, chunk: np.ndarray) -> None:
        self.samples = np.concatenate([self.samples, chunk])
        if len(self.samples) > self.max_samples:
            drop = len(self.samples) - self.max_samples
            self.samples = self.samples[drop:]
            self.start_idx += drop

    def extract(self, abs_start: int, abs_end: int) -> np.ndarray:
        rel_start = max(0, abs_start - self.start_idx)
        rel_end = max(rel_start, abs_end - self.start_idx)
        return self.samples[rel_start:rel_end].copy()


# ── 메인 backend ─────────────────────────────────────────────
class LiveVoiceBackend:
    """
    Parameters
    ----------
    capture : AudioCapture
        결과 cooked frame 을 주입할 큐 (기존 AudioWorker 가 읽음).
    config : BackendConfig
        모든 파라미터.
    """

    def __init__(self, capture: AudioCapture, config: BackendConfig):
        self.capture = capture
        self.cfg = config
        self._stop = threading.Event()
        self._asr_busy = threading.Event()

        self._audio_q: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=200)
        # depth=1: ASR 처리 중이거나 1 개 대기면 drop. 큐 자체도 maxsize=1.
        self._asr_q: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=1)

        self._stream: Any = None
        self._vad_thread: Optional[threading.Thread] = None
        self._asr_thread: Optional[threading.Thread] = None

        # VAD/ASR 은 lazy-load (start 시)
        self._silero_model: Any = None
        self._vad_iter: Any = None
        self._whisper: Any = None
        self._buffer: Optional[_AudioBuffer] = None

    # ── context manager ────────────────────────────────────
    def __enter__(self) -> "LiveVoiceBackend":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    # ── lifecycle ──────────────────────────────────────────
    def start(self) -> None:
        if self.cfg.audio.mic_gain_percent is not None:
            apply_mic_gain(
                int(self.cfg.audio.mic_gain_percent),
                self.cfg.audio.gain_target_source,
            )

        self._load_models()
        self._open_stream()

        self._vad_thread = threading.Thread(target=self._vad_loop, name="live-voice-vad", daemon=True)
        self._asr_thread = threading.Thread(target=self._asr_loop, name="live-voice-asr", daemon=True)
        self._vad_thread.start()
        self._asr_thread.start()
        _LOGGER.info("LiveVoiceBackend started")

    def stop(self) -> None:
        self._stop.set()
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                _LOGGER.warning("stream close error: %s", e)
            self._stream = None
        for t in (self._vad_thread, self._asr_thread):
            if t is not None:
                t.join(timeout=2.0)
        _LOGGER.info("LiveVoiceBackend stopped")

    # ── internals ──────────────────────────────────────────
    def _load_models(self) -> None:
        from silero_vad import VADIterator, load_silero_vad  # lazy import
        from faster_whisper import WhisperModel  # lazy import

        _LOGGER.info("loading silero-vad (threshold=%.2f)", self.cfg.vad.threshold)
        self._silero_model = load_silero_vad(onnx=True)
        self._vad_iter = VADIterator(
            self._silero_model,
            threshold=self.cfg.vad.threshold,
            sampling_rate=self.cfg.vad.sample_rate,
            min_silence_duration_ms=self.cfg.vad.min_silence_duration_ms,
            speech_pad_ms=self.cfg.vad.speech_pad_ms,
        )
        self._buffer = _AudioBuffer(max_seconds=30.0, sample_rate=self.cfg.vad.sample_rate)

        _LOGGER.info(
            "loading faster-whisper '%s' (compute_type=%s, device=%s)...",
            self.cfg.asr.model, self.cfg.asr.compute_type, self.cfg.asr.device,
        )
        self._whisper = WhisperModel(
            self.cfg.asr.model,
            device=self.cfg.asr.device,
            compute_type=self.cfg.asr.compute_type,
        )
        _LOGGER.info("models ready")

    def _open_stream(self) -> None:
        import sounddevice as sd  # lazy import

        device = self._resolve_device(sd)
        _LOGGER.info(
            "opening audio device=%r rate=%d blocksize=%d ch=%d dtype=%s",
            device, self.cfg.audio.sample_rate, self.cfg.audio.blocksize,
            self.cfg.audio.channels, self.cfg.audio.dtype,
        )
        self._stream = sd.InputStream(
            samplerate=self.cfg.audio.sample_rate,
            channels=self.cfg.audio.channels,
            blocksize=self.cfg.audio.blocksize,
            dtype=self.cfg.audio.dtype,
            device=device,
            callback=self._audio_callback,
        )
        self._stream.start()

    def _resolve_device(self, sd: Any) -> Any:
        hint = self.cfg.audio.device
        if hint is None:
            return None
        try:
            for idx, dev in enumerate(sd.query_devices()):
                if hint in dev["name"] and dev["max_input_channels"] > 0:
                    return idx
        except Exception:
            pass
        return hint  # 이름 문자열도 PortAudio 가 받음

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        if status:
            _LOGGER.debug("audio status: %s", status)
        mono = indata[:, 0].astype(np.float32, copy=True)
        try:
            self._audio_q.put_nowait(mono)
        except queue.Full:
            _LOGGER.warning("audio queue full, dropping chunk")

    def _vad_loop(self) -> None:
        import torch  # lazy import

        assert self._buffer is not None
        seg_start: Optional[int] = None

        while not self._stop.is_set():
            try:
                chunk = self._audio_q.get(timeout=0.2)
            except queue.Empty:
                continue

            if len(chunk) != _EXPECTED_CHUNK:
                _LOGGER.error("unexpected chunk size %d (expected %d)", len(chunk), _EXPECTED_CHUNK)
                continue

            self._buffer.push(chunk)
            tensor = torch.from_numpy(chunk)
            event = self._vad_iter(tensor, return_seconds=False)

            if event is None:
                continue

            if "start" in event:
                seg_start = int(event["start"])
                continue

            if "end" in event:
                end_sample = int(event["end"])
                start_sample = seg_start if seg_start is not None else 0
                seg_start = None
                duration_ms = int((end_sample - start_sample) / self.cfg.vad.sample_rate * 1000)
                if duration_ms < self.cfg.vad.min_speech_ms:
                    _LOGGER.debug("drop short utterance %dms", duration_ms)
                    continue

                # depth=1 규칙
                if self.cfg.drop_while_busy and (
                    self._asr_busy.is_set() or self._asr_q.qsize() > 0
                ):
                    _LOGGER.info("BUSY drop utterance dur=%dms (ASR working)", duration_ms)
                    continue

                audio = self._buffer.extract(start_sample, end_sample)
                try:
                    self._asr_q.put_nowait(audio)
                except queue.Full:
                    _LOGGER.info("asr_queue full, dropping utterance")

    def _asr_loop(self) -> None:
        while not self._stop.is_set():
            try:
                audio = self._asr_q.get(timeout=0.2)
            except queue.Empty:
                continue
            self._asr_busy.set()
            try:
                self._transcribe_and_feed(audio)
            finally:
                self._asr_busy.clear()

    def _transcribe_and_feed(self, audio: np.ndarray) -> None:
        t0 = time.perf_counter()
        try:
            segments, info = self._whisper.transcribe(
                audio,
                language=self.cfg.asr.language,
                beam_size=self.cfg.asr.beam_size,
                no_speech_threshold=self.cfg.asr.no_speech_threshold,
                condition_on_previous_text=self.cfg.asr.condition_on_previous_text,
            )
            segs = list(segments)
        except Exception as e:
            _LOGGER.warning("whisper transcribe error: %s", e)
            return
        decode_ms = int((time.perf_counter() - t0) * 1000)

        if not segs:
            _LOGGER.info("asr empty (decode=%dms)", decode_ms)
            return

        text = " ".join(s.text.strip() for s in segs).strip()
        n = len(segs)
        avg_logprob = sum(s.avg_logprob for s in segs) / n
        no_speech_prob = sum(s.no_speech_prob for s in segs) / n

        _LOGGER.info(
            "asr decode=%dms text='%s' logprob=%.2f no_speech=%.2f",
            decode_ms, text, avg_logprob, no_speech_prob,
        )

        if avg_logprob < self.cfg.asr.min_logprob:
            _LOGGER.info("drop low-confidence utterance (logprob=%.2f < %.2f)",
                         avg_logprob, self.cfg.asr.min_logprob)
            return

        confidence = max(0.0, min(1.0, 1.0 - no_speech_prob))
        self._feed_frames(text, confidence)

    def _feed_frames(self, text: str, confidence: float) -> None:
        """스텁 VAD/STT 가 소비할 cooked frame 시퀀스 주입.

        1회 발화 = (speech start 플래그) + (transcript 프레임) + (silence 프레임 × N)
        """
        self.capture.feed({"speech": True})
        self.capture.feed({"speech": True, "transcript": text, "confidence": confidence})
        for _ in range(max(1, self.cfg.silence_frames_to_feed)):
            self.capture.feed({"speech": False})
