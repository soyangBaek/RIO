"""Live mic backends for RIO.

Phase 1 layout:
  - Python backend keeps the previous all-Python mic/VAD/ASR pipeline.
  - Rust backend moves mic capture + RMS VAD + utterance assembly to a sidecar
    worker, while Python still runs faster-whisper and feeds AudioCapture.

Both backends preserve the existing cooked-frame protocol:
  1. {"speech": True}
  2. {"speech": True, "transcript": ..., "confidence": ...}
  3. {"speech": False} x silence_frames_to_feed
"""
from __future__ import annotations

import base64
import json
import logging
import math
import queue
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Protocol

import numpy as np

from src.app.adapters.audio.capture import AudioCapture
from src.app.adapters.audio.mic_gain import apply_mic_gain, ensure_default_input_source
from src.app.adapters.audio.preprocessor import preprocess_audio
from src.app.core.config import resolve_repo_path
from src.app.core.safety.tick_metrics import increment as increment_metric
from src.app.core.safety.tick_metrics import record as record_metric


_LOGGER = logging.getLogger(__name__)


def _ts() -> str:
    t = time.time()
    return time.strftime("%H:%M:%S", time.localtime(t)) + f".{int((t - int(t)) * 1000):03d}"


class VoiceBackend(Protocol):
    def start(self) -> None:
        ...

    def stop(self) -> None:
        ...

    def set_trace_sink(self, sink: Callable[[str], None] | None) -> None:
        ...


@dataclass
class BackendLaunchConfig:
    type: str = "rust"
    worker_path: str = "native/bin/rio-audio-worker"
    fallback_to_python: bool = True
    startup_timeout_ms: int = 3000


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
    initial_prompt: Optional[str] = None
    # utterance 길이 상한(ms). 이보다 긴 오디오 세그먼트는 whisper 에 투입
    # 하지 않는다. 정상 한국어 단발 명령은 1~2 초 수준 (min_silence=500ms
    # 포함). 3 초 초과는 대부분 노이즈 바다로 VAD 가 길게 이어붙인 케이스.
    # 긴 노이즈를 decode 하느라 ASR 이 BUSY 에 묶여 뒤 발화가 drop 되는
    # 문제(시끄러운 환경) 를 사전에 막는다. 0 이면 가드 해제.
    max_utterance_ms: int = 3000
    # faster-whisper 내부 silero VAD 로 비음성 구간 사전 제거. 시끄러운
    # 환경에서 세그먼트 내부 비음성 구간 (숨소리/정적/배경) 을 빼서 실제
    # decode 분량을 줄인다. silero 모델 CPU 추가분은 Pi 5 에서 작음.
    vad_filter: bool = True


@dataclass
class PreprocessParams:
    enabled: bool = False
    apply_highpass: bool = True
    highpass_cutoff: float = 0.01
    apply_gate: bool = True
    gate_threshold: float = 0.01
    apply_normalize: bool = True
    target_rms: float = 0.1


@dataclass
class BackendConfig:
    audio: AudioParams
    vad: VADParams
    asr: ASRParams
    drop_while_busy: bool = True
    silence_frames_to_feed: int = 2  # keep in sync with stub VAD defaults
    launch: BackendLaunchConfig = field(default_factory=BackendLaunchConfig)
    preprocess: PreprocessParams = field(default_factory=PreprocessParams)


@dataclass
class _VadDecision:
    started: bool = False
    confirmed: bool = False
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
        self._confirmed = False
        self._voiced_samples = 0
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

    def _check_confirmed(self) -> bool:
        """Return True on the chunk where voiced duration first crosses min_speech_ms."""
        if self._confirmed:
            return False
        voiced_ms = (self._voiced_samples / self.sample_rate) * 1000.0
        if voiced_ms >= self.min_speech_ms:
            self._confirmed = True
            return True
        return False

    def process(self, chunk: np.ndarray) -> _VadDecision:
        rms = self._rms(chunk)
        voiced = rms >= self.threshold

        if not self._active:
            if voiced:
                self._active = True
                self._confirmed = False
                self._voiced_samples = len(chunk)
                self._silent_chunks = 0
                self._pending_silence = []
                self._current_chunks = list(self._pre_roll)
                self._current_chunks.append(chunk.copy())
                self._pre_roll.clear()
                return _VadDecision(
                    started=True,
                    confirmed=self._check_confirmed(),
                    rms=rms,
                )
            if self.speech_pad_chunks > 0:
                self._pre_roll.append(chunk.copy())
            return _VadDecision(rms=rms)

        if voiced:
            if self._pending_silence:
                self._current_chunks.extend(self._pending_silence)
                self._pending_silence = []
            self._silent_chunks = 0
            self._current_chunks.append(chunk.copy())
            self._voiced_samples += len(chunk)
            return _VadDecision(
                confirmed=self._check_confirmed(),
                rms=rms,
            )

        self._pending_silence.append(chunk.copy())
        self._silent_chunks += 1
        if self._silent_chunks < self.silence_chunks_to_end:
            return _VadDecision(rms=rms)

        trailing_pad = self._pending_silence[-self.speech_pad_chunks :] if self.speech_pad_chunks > 0 else []
        segment_chunks = self._current_chunks + trailing_pad
        audio = np.concatenate(segment_chunks) if segment_chunks else np.zeros(0, dtype=np.float32)
        duration_ms = int(round((len(audio) / self.sample_rate) * 1000.0))

        self._active = False
        self._confirmed = False
        self._voiced_samples = 0
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


class _WhisperBridgeBackend:
    def __init__(self, capture: AudioCapture, config: BackendConfig):
        self.capture = capture
        self.cfg = config
        self._trace_sink: Callable[[str], None] | None = None
        self._whisper: Any = None

    def set_trace_sink(self, sink: Callable[[str], None] | None) -> None:
        self._trace_sink = sink

    def _emit_trace(self, message: str) -> None:
        if self._trace_sink is not None:
            self._trace_sink(f"[{_ts()}] {message}")

    def _prepare_input_source(self) -> None:
        device_hint = str(self.cfg.audio.device or "").strip().lower()
        if device_hint not in {"pulse", "default"}:
            return
        ensure_default_input_source(self.cfg.audio.gain_target_source)

    def _ensure_whisper(self) -> None:
        if self._whisper is not None:
            return
        from faster_whisper import WhisperModel  # lazy import

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

    def _transcribe_and_feed(self, audio: np.ndarray) -> None:
        self._ensure_whisper()

        # 긴 세그먼트 사전 drop. 정상 단발 명령은 1~2초라 3초 초과는 대부분
        # 시끄러운 환경에서 VAD 가 노이즈를 길게 이어붙인 경우. whisper 호출
        # 자체를 건너뛰어 ASR 이 BUSY 에 묶이지 않게 함 → 뒤 발화 drop 방지.
        sample_rate = max(1, int(self.cfg.audio.sample_rate))
        audio_ms = int((audio.size / sample_rate) * 1000) if audio.size else 0
        max_utt_ms = int(self.cfg.asr.max_utterance_ms or 0)
        if max_utt_ms > 0 and audio_ms > max_utt_ms:
            _LOGGER.info(
                "drop long utterance dur=%dms > %dms (likely noise, ASR skipped)",
                audio_ms,
                max_utt_ms,
            )
            self._emit_trace(
                f"[voice.asr] DROP_LONG dur={audio_ms}ms threshold={max_utt_ms}ms"
            )
            increment_metric("asr_long_drop_count")
            self._feed_silence()
            return

        pre = self.cfg.preprocess
        if pre.enabled and audio.size > 0:
            pre_t0 = time.perf_counter()
            audio = preprocess_audio(
                audio,
                sample_rate=self.cfg.audio.sample_rate,
                apply_highpass=pre.apply_highpass,
                apply_gate=pre.apply_gate,
                apply_normalize=pre.apply_normalize,
                gate_threshold=pre.gate_threshold,
                highpass_cutoff=pre.highpass_cutoff,
                target_rms=pre.target_rms,
            )
            pre_ms = int((time.perf_counter() - pre_t0) * 1000)
            _LOGGER.debug("preprocess applied %dms (samples=%d)", pre_ms, audio.size)
        t0 = time.perf_counter()
        try:
            segments, _info = self._whisper.transcribe(
                audio,
                language=self.cfg.asr.language,
                beam_size=self.cfg.asr.beam_size,
                no_speech_threshold=self.cfg.asr.no_speech_threshold,
                condition_on_previous_text=self.cfg.asr.condition_on_previous_text,
                initial_prompt=self.cfg.asr.initial_prompt,
                # Base 모델이 짧은 한국어 명령에서 "X X X..." 반복 루프에
                # 빠지는 문제 방어. 기본 2.4 → 1.8 로 낮추면 반복 생성이
                # 감지되자마자 해당 fallback 경로로 빠르게 포기한다.
                compression_ratio_threshold=1.8,
                # silero 기반 내부 VAD. 세그먼트 내부 비음성 구간을 빼서
                # 실제 디코딩 분량을 줄인다 (시끄러운 환경에서 장시간
                # decode 원인 감소).
                vad_filter=bool(self.cfg.asr.vad_filter),
            )
            segs = list(segments)
        except Exception as exc:
            _LOGGER.warning("whisper transcribe error: %s", exc)
            self._emit_trace(f"[voice.asr] ERROR {exc}")
            self._feed_silence()
            return
        decode_ms = int((time.perf_counter() - t0) * 1000)
        record_metric("asr_decode_ms", float(decode_ms))

        if not segs:
            _LOGGER.info("asr empty (decode=%dms)", decode_ms)
            self._emit_trace(f"[voice.asr] EMPTY decode={decode_ms}ms")
            increment_metric("asr_empty_count")
            self._feed_silence()
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
            self._feed_silence()
            return

        confidence = max(0.0, min(1.0, 1.0 - no_speech_prob))
        self._feed_frames(text, confidence)

    def _feed_frames(self, text: str, confidence: float) -> None:
        self.capture.feed({"speech": True})
        self.capture.feed({"speech": True, "transcript": text, "confidence": confidence})
        for _ in range(max(1, self.cfg.silence_frames_to_feed)):
            self.capture.feed({"speech": False})

    def _feed_silence(self) -> None:
        for _ in range(max(1, self.cfg.silence_frames_to_feed)):
            self.capture.feed({"speech": False})


class PythonLiveVoiceBackend(_WhisperBridgeBackend):
    def __init__(self, capture: AudioCapture, config: BackendConfig):
        super().__init__(capture, config)
        self._stop = threading.Event()
        self._asr_busy = threading.Event()

        self._audio_q: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=200)
        self._asr_q: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=1)

        self._stream: Any = None
        self._vad_thread: Optional[threading.Thread] = None
        self._asr_thread: Optional[threading.Thread] = None
        self._vad_engine: _RmsVoiceActivityDetector | None = None

    def __enter__(self) -> "PythonLiveVoiceBackend":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    def start(self) -> None:
        self._stop.clear()
        self._asr_busy.clear()

        self._prepare_input_source()
        if self.cfg.audio.mic_gain_percent is not None:
            apply_mic_gain(
                int(self.cfg.audio.mic_gain_percent),
                self.cfg.audio.gain_target_source,
            )

        self._load_vad_engine()
        self._ensure_whisper()
        self._open_stream()

        self._vad_thread = threading.Thread(target=self._vad_loop, name="live-voice-vad", daemon=True)
        self._asr_thread = threading.Thread(target=self._asr_loop, name="live-voice-asr", daemon=True)
        self._vad_thread.start()
        self._asr_thread.start()
        _LOGGER.info("PythonLiveVoiceBackend started")

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
        _LOGGER.info("PythonLiveVoiceBackend stopped")

    def _load_vad_engine(self) -> None:
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

        threshold = int(self.cfg.vad.threshold)
        window_rms: list[int] = []
        last_window_log = time.monotonic()

        while not self._stop.is_set():
            try:
                chunk = self._audio_q.get(timeout=0.2)
            except queue.Empty:
                continue

            decision = self._vad_engine.process(chunk)

            window_rms.append(decision.rms)
            now_mono = time.monotonic()
            if now_mono - last_window_log >= 0.5 and window_rms:
                rms_min = min(window_rms)
                rms_max = max(window_rms)
                rms_avg = int(sum(window_rms) / len(window_rms))
                _LOGGER.debug(
                    "vad rms samples=%d min=%d avg=%d max=%d threshold=%d",
                    len(window_rms),
                    rms_min,
                    rms_avg,
                    rms_max,
                    threshold,
                )
                window_rms.clear()
                last_window_log = now_mono

            if decision.started:
                self._emit_trace(f"[voice.vad] speech START rms={decision.rms}")

            if decision.confirmed:
                self._emit_trace(f"[voice.vad] speech CONFIRMED rms={decision.rms}")
                self.capture.feed({"speech": True})

            if not decision.ended or decision.audio is None:
                continue

            if decision.duration_ms < self.cfg.vad.min_speech_ms:
                self._emit_trace(
                    f"[voice.vad] speech END dur={decision.duration_ms}ms "
                    f"peak={decision.peak:.3f} rms={decision.segment_rms:.3f} -> DROP_SHORT"
                )
                self._feed_silence()
                continue

            # 구간 평균 RMS 가 너무 낮으면 whisper 로 보내지 않는다.
            # 관찰: 스파이크로 시작됐지만 실제 발화가 거의 없는 오디오
            # (segment_rms < 0.05) 가 들어가면 base 모델이 "자" 같은 단일
            # 글자 hallucination 루프에 빠져 16 초+ 디코딩 + BUSY drop
            # 연쇄 발생. 정상 발화는 segment_rms ≈ 0.15~0.4 수준이라
            # 0.05 하한은 여유가 있다.
            if decision.segment_rms < 0.05:
                _LOGGER.info(
                    "drop quiet utterance dur=%dms rms=%.3f (likely noise spike)",
                    decision.duration_ms,
                    decision.segment_rms,
                )
                self._emit_trace(
                    f"[voice.vad] speech END dur={decision.duration_ms}ms "
                    f"rms={decision.segment_rms:.3f} -> DROP_QUIET"
                )
                self._feed_silence()
                continue

            self._emit_trace(
                f"[voice.vad] speech END dur={decision.duration_ms}ms "
                f"peak={decision.peak:.3f} rms={decision.segment_rms:.3f}"
            )

            if self.cfg.drop_while_busy and (self._asr_busy.is_set() or self._asr_q.qsize() > 0):
                _LOGGER.info("BUSY drop utterance dur=%dms (ASR working)", decision.duration_ms)
                self._emit_trace(f"[voice.asr] BUSY drop dur={decision.duration_ms}ms")
                increment_metric("asr_busy_drop_count")
                self._feed_silence()
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


class RustAudioBackend(_WhisperBridgeBackend):
    def __init__(
        self,
        capture: AudioCapture,
        config: BackendConfig,
        *,
        config_path: str | Path = "configs/voice.yaml",
    ) -> None:
        super().__init__(capture, config)
        self.config_path = str(config_path)
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._asr_busy = threading.Event()
        self._process: subprocess.Popen[str] | None = None
        self._stdout_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None
        self._decode_thread: Optional[threading.Thread] = None
        self._utterance_q: "queue.Queue[np.ndarray | None]" = queue.Queue(maxsize=2)
        self._stdin_lock = threading.Lock()

    def start(self) -> None:
        self._stop.clear()
        self._ready.clear()
        self._asr_busy.clear()

        self._prepare_input_source()
        if self.cfg.audio.mic_gain_percent is not None:
            apply_mic_gain(
                int(self.cfg.audio.mic_gain_percent),
                self.cfg.audio.gain_target_source,
            )

        self._ensure_whisper()
        worker_path = self._resolve_worker_path()
        cmd = [str(worker_path), "--config", str(resolve_repo_path(self.config_path))]
        _LOGGER.info("starting rust audio worker: %s", " ".join(cmd))
        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        self._stdout_thread = threading.Thread(target=self._stdout_loop, name="rust-audio-stdout", daemon=True)
        self._stderr_thread = threading.Thread(target=self._stderr_loop, name="rust-audio-stderr", daemon=True)
        self._decode_thread = threading.Thread(target=self._decode_loop, name="rust-audio-decode", daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()
        self._decode_thread.start()

        timeout_s = max(0.5, self.cfg.launch.startup_timeout_ms / 1000.0)
        if not self._ready.wait(timeout=timeout_s):
            self.stop()
            raise RuntimeError("Rust audio worker did not become ready in time")

        _LOGGER.info("RustAudioBackend started")

    def stop(self) -> None:
        self._stop.set()
        self._send_command({"type": "shutdown"})
        try:
            self._utterance_q.put_nowait(None)
        except queue.Full:
            pass

        process = self._process
        if process is not None:
            try:
                process.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1.0)
        for thread in (self._stdout_thread, self._stderr_thread, self._decode_thread):
            if thread is not None:
                thread.join(timeout=2.0)
        self._stdout_thread = None
        self._stderr_thread = None
        self._decode_thread = None
        self._process = None
        _LOGGER.info("RustAudioBackend stopped")

    def _resolve_worker_path(self) -> Path:
        raw_path = self.cfg.launch.worker_path
        candidate = resolve_repo_path(raw_path)
        if candidate.exists():
            return candidate
        return Path(raw_path)

    def _stdout_loop(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                _LOGGER.warning("invalid rust worker message: %s", line)
                continue
            self._handle_worker_message(message)

    def _stderr_loop(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        for raw_line in process.stderr:
            line = raw_line.strip()
            if line:
                _LOGGER.info("[rust-audio] %s", line)

    def _handle_worker_message(self, message: dict[str, Any]) -> None:
        kind = str(message.get("type") or "")
        if kind == "ready":
            self._ready.set()
            return
        if kind == "speech_started":
            self._emit_trace(f"[voice.vad] speech START rms={int(message.get('rms', 0))}")
            return
        if kind == "speech_confirmed":
            self._emit_trace(f"[voice.vad] speech CONFIRMED rms={int(message.get('rms', 0))}")
            self.capture.feed({"speech": True})
            return
        if kind == "speech_ended":
            dropped_short = bool(message.get("dropped_short"))
            dropped_quiet = bool(message.get("dropped_quiet"))
            suffix = ""
            if dropped_short:
                suffix = " -> DROP_SHORT"
            elif dropped_quiet:
                suffix = " -> DROP_QUIET"
            self._emit_trace(
                f"[voice.vad] speech END dur={int(message.get('duration_ms', 0))}ms "
                f"peak={float(message.get('peak', 0.0)):.3f} "
                f"rms={float(message.get('rms', 0.0)):.3f}{suffix}"
            )
            if dropped_short or dropped_quiet:
                self._feed_silence()
            return
        if kind == "busy_drop":
            self._emit_trace(f"[voice.asr] BUSY drop dur={int(message.get('duration_ms', 0))}ms")
            self._feed_silence()
            return
        if kind == "trace":
            text = str(message.get("message") or "").strip()
            if text:
                self._emit_trace(text)
            return
        if kind == "error":
            text = str(message.get("message") or "unknown rust worker error")
            _LOGGER.warning("rust audio worker error: %s", text)
            self._emit_trace(f"[voice.worker] ERROR {text}")
            return
        if kind == "utterance":
            encoded = str(message.get("pcm_f32_b64") or "")
            if not encoded:
                return
            try:
                audio = np.frombuffer(base64.b64decode(encoded), dtype=np.float32).copy()
            except Exception as exc:  # pragma: no cover - defensive
                _LOGGER.warning("failed to decode utterance from rust worker: %s", exc)
                return
            try:
                self._utterance_q.put_nowait(audio)
            except queue.Full:
                _LOGGER.info("decode queue full, dropping utterance from rust worker")
                self._emit_trace("[voice.asr] queue full, dropping utterance")
            return

    def _decode_loop(self) -> None:
        while not self._stop.is_set():
            try:
                audio = self._utterance_q.get(timeout=0.2)
            except queue.Empty:
                continue
            if audio is None:
                return
            self._asr_busy.set()
            self._send_command({"type": "asr_busy"})
            try:
                self._transcribe_and_feed(audio)
            finally:
                self._asr_busy.clear()
                self._send_command({"type": "asr_idle"})

    def _send_command(self, payload: dict[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            return
        line = json.dumps(payload, ensure_ascii=False)
        with self._stdin_lock:
            try:
                process.stdin.write(line + "\n")
                process.stdin.flush()
            except BrokenPipeError:
                return


class LiveVoiceBackend(PythonLiveVoiceBackend):
    """Compatibility alias for tests and existing imports."""


__all__ = [
    "ASRParams",
    "AudioParams",
    "BackendConfig",
    "BackendLaunchConfig",
    "LiveVoiceBackend",
    "PreprocessParams",
    "PythonLiveVoiceBackend",
    "RustAudioBackend",
    "VADParams",
    "VoiceBackend",
    "_RmsVoiceActivityDetector",
]
