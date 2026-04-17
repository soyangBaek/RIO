"""mic → VAD → ASR → wake word → log/save 파이프라인.

스레드 구조:
  - PortAudio callback → audio_queue (float32 청크)
  - main thread       : audio_queue 에서 꺼내 VAD 처리 → 완성된 utterance 를 asr_queue 로
  - asr worker thread : asr_queue 에서 utterance 꺼내 Whisper 돌리고 result_queue 로
  - main thread       : result_queue 에서 결과 꺼내 wake word 결정 + 로그 + 녹음 저장

ASR 을 별도 스레드로 분리한 이유:
  Whisper 디코딩이 수백 ms~수 초 걸리는 동안 메인 루프가 audio_queue 를 비우지 못하면
  PortAudio 콜백이 계속 청크를 넣어 overflow("queue full") 가 발생한다.
"""
from __future__ import annotations

import queue
import signal
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import numpy as np

from .asr_whisper import ASRConfig, ASRResult, WhisperASR
from .audio_source import AudioConfig, AudioSource
from .recorder import UtteranceRecorder
from .vad_silero import SileroVAD, UtteranceMeta, VADConfig
from .wake_word import WakeConfig, WakeDecision, WakeWordDetector


def _ts() -> str:
    t = time.time()
    return time.strftime("%H:%M:%S", time.localtime(t)) + f".{int((t - int(t)) * 1000):03d}"


_WAKE_TAG = {
    "wake": "WAKE       ",
    "wake+cmd": "WAKE+CMD   ",
    "cmd": "CMD        ",
    "ignored": "IGNORED    ",
    "reject_logprob": "REJECT     ",
}


# 최근 활동이 없을 때 주기적으로 heartbeat 를 찍는 간격(s).
# 현재 mic 레벨/큐 깊이/wake 상태를 한 줄로 보여 줘서 "프로세스는 돌지만 아무 반응 없음" 판별에 사용.
_HEARTBEAT_INTERVAL_S = 5.0


@dataclass
class _PendingUtterance:
    audio: np.ndarray
    meta: UtteranceMeta


@dataclass
class _AsrOutput:
    audio: np.ndarray
    meta: UtteranceMeta
    result: ASRResult


class Pipeline:
    def __init__(
        self,
        audio_cfg: AudioConfig,
        vad_cfg: VADConfig,
        asr_cfg: ASRConfig,
        wake_cfg: WakeConfig,
        recorder: UtteranceRecorder,
    ):
        self.audio_cfg = audio_cfg
        self.vad_cfg = vad_cfg
        self.asr_cfg = asr_cfg
        self.wake_cfg = wake_cfg
        self.recorder = recorder

        self.vad = SileroVAD(vad_cfg)
        self.asr = WhisperASR(asr_cfg)
        self.wake = WakeWordDetector(wake_cfg)

        self.audio_q: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=200)
        # depth=1 규칙: ASR 큐에 1개만 허용. ASR 처리 중(asr_busy)이거나 이미 대기 중이면
        # 새 utterance 는 즉시 drop (한 번에 하나만 처리).
        self.asr_q: "queue.Queue[_PendingUtterance]" = queue.Queue(maxsize=1)
        self.result_q: "queue.Queue[_AsrOutput]" = queue.Queue(maxsize=16)

        self.source = AudioSource(audio_cfg, self.audio_q)
        self._stop = threading.Event()
        self._asr_busy = threading.Event()
        self._asr_thread: Optional[threading.Thread] = None

    def _handle_sigint(self, *_args) -> None:
        self._stop.set()

    def run(self) -> None:
        signal.signal(signal.SIGINT, self._handle_sigint)
        self._asr_thread = threading.Thread(target=self._asr_loop, name="asr", daemon=True)
        self._asr_thread.start()
        self.source.start()
        print(f"[{_ts()}] [pipeline] running. Ctrl+C to stop.")
        print(f"[{_ts()}] [pipeline] wake phrase='{self.wake_cfg.phrase}' "
              f"aliases={self.wake_cfg.aliases} state={self.wake.state.value}")

        last_heartbeat = time.monotonic()
        try:
            while not self._stop.is_set():
                self._drain_results()

                now = time.monotonic()
                if now - last_heartbeat >= _HEARTBEAT_INTERVAL_S:
                    self._print_heartbeat()
                    last_heartbeat = now

                try:
                    chunk = self.audio_q.get(timeout=0.1)
                except queue.Empty:
                    continue

                utt = self.vad.process(chunk)
                if utt is None:
                    continue
                audio, meta = utt
                if not meta.passed_min_speech:
                    self._handle_short_drop(audio, meta)
                    continue

                # depth=1 정책: ASR 처리 중이거나 큐 비어있지 않으면 즉시 drop.
                if self._asr_busy.is_set() or self.asr_q.qsize() > 0:
                    print(f"[{_ts()}] [pipeline] BUSY drop "
                          f"dur={meta.duration_ms}ms (ASR working on prev utterance)")
                    continue

                try:
                    self.asr_q.put_nowait(_PendingUtterance(audio=audio, meta=meta))
                    print(f"[{_ts()}] [pipeline] → asr_queue (depth={self.asr_q.qsize()})")
                except queue.Full:
                    print(f"[{_ts()}] [pipeline] asr_queue full, dropping utterance")
        finally:
            self._stop.set()
            self.source.stop()
            if self._asr_thread is not None:
                self._asr_thread.join(timeout=2.0)
            self._drain_results()
            print(f"[{_ts()}] [pipeline] stopped.")

    def _print_heartbeat(self) -> None:
        print(
            f"[{_ts()}] [.] state={self.wake.state.value}  "
            f"audio_q={self.audio_q.qsize()}  asr_q={self.asr_q.qsize()}  "
            f"mic peak={self.vad.last_chunk_peak:.3f} rms={self.vad.last_chunk_rms:.3f}"
        )

    # ── internals ────────────────────────────────────────────
    def _asr_loop(self) -> None:
        while not self._stop.is_set():
            try:
                item = self.asr_q.get(timeout=0.2)
            except queue.Empty:
                continue
            self._asr_busy.set()
            try:
                print(f"[{_ts()}] [asr] decoding {item.meta.duration_ms}ms of audio...")
                try:
                    result = self.asr.transcribe(item.audio)
                except Exception as e:
                    print(f"[{_ts()}] [asr] error: {e}")
                    continue
                logprob_str = (
                    f"{result.avg_logprob:.2f}"
                    if result.avg_logprob != -float("inf") else "-inf"
                )
                print(
                    f"[{_ts()}] [asr] done decode={result.decode_ms}ms "
                    f"text='{result.text}' "
                    f"logprob={logprob_str} no_speech={result.no_speech_prob:.2f} "
                    f"lang={result.language}"
                )
                try:
                    self.result_q.put_nowait(_AsrOutput(audio=item.audio, meta=item.meta, result=result))
                except queue.Full:
                    print(f"[{_ts()}] [pipeline] result_queue full, dropping")
            finally:
                self._asr_busy.clear()

    def _drain_results(self) -> None:
        while True:
            try:
                out = self.result_q.get_nowait()
            except queue.Empty:
                return
            self._handle_utterance(out.audio, out.meta, out.result)

    def _handle_short_drop(self, audio: np.ndarray, meta: UtteranceMeta) -> None:
        # VAD END 라인에서 이미 "→ DROP" 을 찍었으므로 추가 로그는 생략.
        label = "drop_tooshort"
        sidecar = {
            "timestamp": datetime.now().astimezone().isoformat(),
            "label": label,
            "duration_ms": meta.duration_ms,
            "vad": self._vad_snapshot(meta),
            "asr": None,
            "wake": None,
        }
        self.recorder.save(audio, label, "", sidecar)

    def _handle_utterance(self, audio: np.ndarray, meta: UtteranceMeta, asr: ASRResult) -> None:
        decision = self.wake.decide(asr.text, asr.avg_logprob)
        tag = _WAKE_TAG.get(decision.label, decision.label)

        parts: list[str] = []
        if decision.matched_alias is not None:
            parts.append(f"matched='{decision.matched_alias}' edit={decision.edit_distance}")
        if decision.command:
            parts.append(f"cmd='{decision.command}'")
        if decision.label == "reject_logprob":
            parts.append(f"min_logprob={self.wake_cfg.min_asr_logprob}")
        extra = ("  " + "  ".join(parts)) if parts else ""
        print(
            f"[{_ts()}] [wake] {tag} {decision.state_before}→{decision.state_after}"
            f"{extra}"
        )

        sidecar = {
            "timestamp": datetime.now().astimezone().isoformat(),
            "label": decision.label,
            "duration_ms": meta.duration_ms,
            "vad": self._vad_snapshot(meta),
            "asr": {
                "model": self.asr_cfg.model,
                "language": asr.language,
                "text": asr.text,
                "avg_logprob": round(asr.avg_logprob, 3)
                if asr.avg_logprob != -float("inf") else None,
                "no_speech_prob": round(asr.no_speech_prob, 3),
                "compression_ratio": round(asr.compression_ratio, 3),
                "decode_ms": asr.decode_ms,
            },
            "wake": self._wake_snapshot(decision),
        }
        self.recorder.save(audio, decision.label, asr.text or "silent", sidecar)

    def _vad_snapshot(self, meta: UtteranceMeta) -> dict:
        return {
            "threshold": self.vad_cfg.threshold,
            "min_silence_duration_ms": self.vad_cfg.min_silence_duration_ms,
            "speech_pad_ms": self.vad_cfg.speech_pad_ms,
            "min_speech_ms": self.vad_cfg.min_speech_ms,
            "sample_rate": self.vad_cfg.sample_rate,
            "duration_ms": meta.duration_ms,
            "peak": round(meta.peak, 4),
            "rms": round(meta.rms, 4),
            "start_sample": meta.start_sample,
            "end_sample": meta.end_sample,
        }

    def _wake_snapshot(self, decision: WakeDecision) -> dict:
        return {
            "matched_alias": decision.matched_alias,
            "edit_distance": decision.edit_distance,
            "command": decision.command,
            "state_before": decision.state_before,
            "state_after": decision.state_after,
            "config": {
                "phrase": self.wake_cfg.phrase,
                "aliases": self.wake_cfg.aliases,
                "fuzzy": self.wake_cfg.fuzzy,
                "max_edit_distance": self.wake_cfg.max_edit_distance,
                "cooldown_ms": self.wake_cfg.cooldown_ms,
                "listen_window_ms": self.wake_cfg.listen_window_ms,
                "extend_on_command": self.wake_cfg.extend_on_command,
                "min_asr_logprob": self.wake_cfg.min_asr_logprob,
                "strip_from_command": self.wake_cfg.strip_from_command,
            },
        }
