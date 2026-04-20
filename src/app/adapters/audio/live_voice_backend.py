"""실제 mic -> RMS VAD -> Whisper 파이프라인을 백그라운드 스레드로 돌리고,
완성된 utterance 를 기존 AudioCapture 의 feed() 로 주입하는 어댑터.

설계:
  - sounddevice 콜백 스레드가 오디오 청크를 audio_queue 에 push
  - VAD 스레드가 audio_queue 를 빼내 RMS 기반으로 utterance 경계 판정
  - ASR 스레드가 utterance 를 꺼내 faster-whisper 로 전사
  - 전사 결과를 AudioCapture.feed() 로 밀어넣음 (기존 AudioWorker 가 tick 마다 꺼내서 소비)

Frame 주입 프로토콜 (utterance 1건 당):
  1. {"speech": True}                             -> 스텁 VAD 가 STARTED 이벤트 발행
  2. {"speech": True, "transcript": ..., ...}     -> 스텁 STT 가 Transcript 반환
                                                    -> IntentNormalizer 가 voice.intent.* 발행
  3. {"speech": False} x silence_frames_to_end    -> 스텁 VAD 가 ENDED 이벤트 발행

Depth=1 동시성 규칙:
  - ASR 처리 중이거나 이미 대기 utterance 가 있으면 새 발화는 즉시 drop
  - 응답 일관성 + Pi CPU 보호 목적

Context manager 프로토콜:
  - `with LiveVoiceBackend(...) as backend:` 로 써서 start/stop 순서 실수 방지
"""
from __future__ import annotations

import logging
import math
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Optional

import numpy as np

from src.app.adapters.audio.capture import AudioCapture
from src.app.adapters.audio.mic_gain import apply_mic_gain


_LOGGER = logging.getLogger(__name__)


def _ts() -> str:
    t = time.time()
    return time.strftime("%H:%M:%S", time.localtime(t)) + f".{int((t - int(t)) * 1000):03d}"


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
    threshold: int = 350
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


@dataclass
class _VadDecision:
    started: bool = False
    ended: bool = False
    rms: int = 0
    duration_ms: int = 0
    peak: float = 0.0
    segment_rms: float = 0.0
    audio: np.ndarray | None = None


class _RmsVoiceActivityDetector:
    def __init__(
        self,
        *,
        threshold: int,
        silence_chunks_to_end: int,
        speech_pad_chunks: int,
        min_speech_ms: int,
        sample_rate: int,
    ) -> None:
        self.threshold = max(0, threshold)
        self.silence_chunks_to_end = max(1, silence_chunks_to_end)
        self.speech_pad_chunks = max(0, speech_pad_chunks)
        self.min_speech_ms = max(0, min_speech_ms)
        self.sample_rate = max(1, sample_rate)

        self._active = False
        self._silent_chunks = 0
        self._pre_roll: deque[np.ndarray] = (
            deque(maxlen=self.speech_pad_chunks) if self.speech_pad_chunks > 0 else deque()
        )
        self._current_chunks: list[np.ndarray] = []
        self._pending_silence: list[np.ndarray] = []

    @staticmethod
    def _rms(chunk: np.ndarray) -> int:
        if chunk.size == 0:
            return 0
        clipped = np.clip(chunk.astype(np.float32, copy=False), -1.0, 1.0)
        return int(round(float(np.sqrt(np.mean(clipped * clipped))) * 32768.0))

    def process(self, chunk: np.ndarray) -> _VadDecision:
        rms = self._rms(chunk)
        voiced = rms >= self.threshold

        if not self._active:
            if voiced:
                self._active = True
                self._silent_chunks = 0
                self._pending_silence = []
                self._current_chunks = list(self._pre_roll)
                self._current_chunks.append(chunk.copy())
                self._pre_roll.clear()
                return _VadDecision(started=True, rms=rms)
            if self.speech_pad_chunks > 0:
                self._pre_roll.append(chunk.copy())
            return _VadDecision(rms=rms)

        if voiced:
            if self._pending_silence:
                self._current_chunks.extend(self._pending_silence)
                self._pending_silence = []
            self._silent_chunks = 0
            self._current_chunks.append(chunk.copy())
            return _VadDecision(rms=rms)

        self._pending_silence.append(chunk.copy())
        self._silent_chunks += 1
        if self._silent_chunks < self.silence_chunks_to_end:
            return _VadDecision(rms=rms)

        trailing_pad = self._pending_silence[-self.speech_pad_chunks :] if self.speech_pad_chunks > 0 else []
        segment_chunks = self._current_chunks + trailing_pad
        audio = np.concatenate(segment_chunks) if segment_chunks else np.zeros(0, dtype=np.float32)
        duration_ms = int(round((len(audio) / self.sample_rate) * 1000.0))

        self._active = False
        self._silent_chunks = 0
        self._current_chunks = []
        self._pending_silence = []

        return _VadDecision(
            ended=True,
            rms=rms,
            duration_ms=duration_ms,
            peak=float(np.abs(audio).max()) if audio.size else 0.0,
            segment_rms=float(np.sqrt(np.mean(audio * audio))) if audio.size else 0.0,
            audio=audio,
        )


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
        self._asr_q: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=1)

        self._stream: Any = None
        self._vad_thread: Optional[threading.Thread] = None
        self._asr_thread: Optional[threading.Thread] = None

        self._vad_engine: _RmsVoiceActivityDetector | None = None
        self._whisper: Any = None
        self._trace_sink: Callable[[str], None] | None = None

    def __enter__(self) -> "LiveVoiceBackend":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    def set_trace_sink(self, sink: Callable[[str], None] | None) -> None:
        self._trace_sink = sink

    def start(self) -> None:
        self._stop.clear()
        self._asr_busy.clear()

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
            except Exception as exc:
                _LOGGER.warning("stream close error: %s", exc)
            self._stream = None
        for thread in (self._vad_thread, self._asr_thread):
            if thread is not None:
                thread.join(timeout=2.0)
        self._vad_thread = None
        self._asr_thread = None
        _LOGGER.info("LiveVoiceBackend stopped")

    def _emit_trace(self, message: str) -> None:
        if self._trace_sink is not None:
            self._trace_sink(f"[{_ts()}] {message}")

    def _load_models(self) -> None:
        from faster_whisper import WhisperModel  # lazy import

        chunk_ms = max(1.0, (self.cfg.audio.blocksize / self.cfg.audio.sample_rate) * 1000.0)
        silence_chunks_to_end = max(1, int(math.ceil(self.cfg.vad.min_silence_duration_ms / chunk_ms)))
        speech_pad_chunks = max(0, int(math.ceil(self.cfg.vad.speech_pad_ms / chunk_ms)))
        self._vad_engine = _RmsVoiceActivityDetector(
            threshold=int(self.cfg.vad.threshold),
            silence_chunks_to_end=silence_chunks_to_end,
            speech_pad_chunks=speech_pad_chunks,
            min_speech_ms=self.cfg.vad.min_speech_ms,
            sample_rate=self.cfg.vad.sample_rate,
        )
        _LOGGER.info(
            "loading rms-vad (threshold=%d, silence_chunks=%d, pad_chunks=%d)",
            self.cfg.vad.threshold,
            silence_chunks_to_end,
            speech_pad_chunks,
        )

        _LOGGER.info(
            "loading faster-whisper '%s' (compute_type=%s, device=%s)...",
            self.cfg.asr.model,
            self.cfg.asr.compute_type,
            self.cfg.asr.device,
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
            device,
            self.cfg.audio.sample_rate,
            self.cfg.audio.blocksize,
            self.cfg.audio.channels,
            self.cfg.audio.dtype,
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
        return hint

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        del frames, time_info
        if status:
            _LOGGER.debug("audio status: %s", status)
        mono = indata[:, 0]
        if np.issubdtype(mono.dtype, np.integer):
            normalized = mono.astype(np.float32, copy=False) / 32768.0
        else:
            normalized = mono.astype(np.float32, copy=True)
        try:
            self._audio_q.put_nowait(normalized.copy())
        except queue.Full:
            _LOGGER.warning("audio queue full, dropping chunk")

    def _vad_loop(self) -> None:
        assert self._vad_engine is not None

        while not self._stop.is_set():
            try:
                chunk = self._audio_q.get(timeout=0.2)
            except queue.Empty:
                continue

            decision = self._vad_engine.process(chunk)
            if decision.started:
                _LOGGER.debug("speech started (rms=%d)", decision.rms)
                self._emit_trace(f"[voice.vad] speech START rms={decision.rms}")

            if not decision.ended or decision.audio is None:
                continue

            if decision.duration_ms < self.cfg.vad.min_speech_ms:
                _LOGGER.debug("drop short utterance %dms", decision.duration_ms)
                self._emit_trace(
                    f"[voice.vad] speech END dur={decision.duration_ms}ms "
                    f"peak={decision.peak:.3f} rms={decision.segment_rms:.3f} -> DROP_SHORT"
                )
                continue

            self._emit_trace(
                f"[voice.vad] speech END dur={decision.duration_ms}ms "
                f"peak={decision.peak:.3f} rms={decision.segment_rms:.3f}"
            )

            if self.cfg.drop_while_busy and (self._asr_busy.is_set() or self._asr_q.qsize() > 0):
                _LOGGER.info("BUSY drop utterance dur=%dms (ASR working)", decision.duration_ms)
                self._emit_trace(f"[voice.asr] BUSY drop dur={decision.duration_ms}ms")
                continue

            try:
                self._asr_q.put_nowait(decision.audio)
            except queue.Full:
                _LOGGER.info("asr_queue full, dropping utterance")
                self._emit_trace(f"[voice.asr] queue full, dropping dur={decision.duration_ms}ms")

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
            segments, _info = self._whisper.transcribe(
                audio,
                language=self.cfg.asr.language,
                beam_size=self.cfg.asr.beam_size,
                no_speech_threshold=self.cfg.asr.no_speech_threshold,
                condition_on_previous_text=self.cfg.asr.condition_on_previous_text,
            )
            segs = list(segments)
        except Exception as exc:
            _LOGGER.warning("whisper transcribe error: %s", exc)
            self._emit_trace(f"[voice.asr] ERROR {exc}")
            return
        decode_ms = int((time.perf_counter() - t0) * 1000)

        if not segs:
            _LOGGER.info("asr empty (decode=%dms)", decode_ms)
            self._emit_trace(f"[voice.asr] EMPTY decode={decode_ms}ms")
            return

        text = " ".join(segment.text.strip() for segment in segs).strip()
        count = len(segs)
        avg_logprob = sum(segment.avg_logprob for segment in segs) / count
        no_speech_prob = sum(segment.no_speech_prob for segment in segs) / count

        _LOGGER.info(
            "asr decode=%dms text='%s' logprob=%.2f no_speech=%.2f",
            decode_ms,
            text,
            avg_logprob,
            no_speech_prob,
        )
        self._emit_trace(
            f"[voice.asr] text='{text}' decode={decode_ms}ms "
            f"logprob={avg_logprob:.2f} no_speech={no_speech_prob:.2f}"
        )

        if avg_logprob < self.cfg.asr.min_logprob:
            _LOGGER.info(
                "drop low-confidence utterance (logprob=%.2f < %.2f)",
                avg_logprob,
                self.cfg.asr.min_logprob,
            )
            self._emit_trace(
                f"[voice.asr] DROP_LOW_CONF logprob={avg_logprob:.2f} "
                f"threshold={self.cfg.asr.min_logprob:.2f}"
            )
            return

        confidence = max(0.0, min(1.0, 1.0 - no_speech_prob))
        self._feed_frames(text, confidence)

    def _feed_frames(self, text: str, confidence: float) -> None:
        """스텁 VAD/STT 가 소비할 cooked frame 시퀀스 주입.

        1회 발화 = (speech start 플래그) + (transcript 프레임) + (silence 프레임 x N)
        """
        self.capture.feed({"speech": True})
        self.capture.feed({"speech": True, "transcript": text, "confidence": confidence})
        for _ in range(max(1, self.cfg.silence_frames_to_feed)):
            self.capture.feed({"speech": False})
