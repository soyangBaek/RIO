"""mic -> RMS VAD -> ASR -> transcript/intent/wake 테스트 파이프라인."""
from __future__ import annotations

import json
import queue
import signal
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import numpy as np

from src.app.domains.smart_home.payloads import build_smart_home_command
from src.app.domains.speech.intent_parser import IntentParseResult, parse_intent

from .asr_whisper import ASRConfig, ASRResult, WhisperASR
from .audio_source import AudioConfig, AudioSource
from .recorder import UtteranceRecorder
from .rust_frontend import RustAudioFrontend, RustFrontendConfig
from .vad_rms import RmsVAD, UtteranceMeta, VADConfig
from .wake_word import WakeConfig, WakeDecision, WakeWordDetector


def _ts() -> str:
    t = time.time()
    return time.strftime("%H:%M:%S", time.localtime(t)) + f".{int((t - int(t)) * 1000):03d}"


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
        recorder: UtteranceRecorder,
        *,
        mode: str = "intent",
        wake_cfg: WakeConfig | None = None,
        backend_type: str = "python",
        rust_frontend_cfg: RustFrontendConfig | None = None,
    ):
        self.audio_cfg = audio_cfg
        self.vad_cfg = vad_cfg
        self.asr_cfg = asr_cfg
        self.recorder = recorder
        self.mode = mode
        self.backend_type = backend_type

        self.vad = RmsVAD(vad_cfg) if backend_type == "python" else None
        self.asr = WhisperASR(asr_cfg)
        self.wake_cfg = wake_cfg
        self.wake = WakeWordDetector(wake_cfg) if wake_cfg is not None and mode == "wake" else None

        self.audio_q: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=200)
        self.asr_q: "queue.Queue[_PendingUtterance]" = queue.Queue(maxsize=1)
        self.result_q: "queue.Queue[_AsrOutput]" = queue.Queue(maxsize=16)

        self.source = AudioSource(audio_cfg, self.audio_q) if backend_type == "python" else None
        self.rust_frontend = (
            RustAudioFrontend(rust_frontend_cfg)
            if backend_type == "rust" and rust_frontend_cfg is not None
            else None
        )
        self._stop = threading.Event()
        self._asr_busy = threading.Event()
        self._asr_thread: Optional[threading.Thread] = None

    def _handle_sigint(self, *_args) -> None:
        self._stop.set()

    def run(self) -> None:
        signal.signal(signal.SIGINT, self._handle_sigint)
        self._asr_thread = threading.Thread(target=self._asr_loop, name="voice-sandbox-asr", daemon=True)
        self._asr_thread.start()
        if self.rust_frontend is not None:
            self.rust_frontend.start()
        elif self.source is not None:
            self.source.start()

        print(
            f"[{_ts()}] [pipeline] running mode={self.mode} backend={self.backend_type}. Ctrl+C to stop."
        )
        if self.wake_cfg is not None and self.mode == "wake":
            print(
                f"[{_ts()}] [pipeline] wake phrase='{self.wake_cfg.phrase}' "
                f"aliases={self.wake_cfg.aliases} state={self.wake.state.value}"
            )

        last_heartbeat = time.monotonic()
        try:
            while not self._stop.is_set():
                self._drain_results()

                now = time.monotonic()
                if now - last_heartbeat >= _HEARTBEAT_INTERVAL_S:
                    self._print_heartbeat()
                    last_heartbeat = now

                if self.rust_frontend is not None:
                    self._poll_rust_frontend()
                else:
                    self._poll_python_frontend()
        finally:
            self._stop.set()
            if self.source is not None:
                self.source.stop()
            if self.rust_frontend is not None:
                self.rust_frontend.stop()
            if self._asr_thread is not None:
                self._asr_thread.join(timeout=2.0)
            self._drain_results()
            print(f"[{_ts()}] [pipeline] stopped.")

    def _print_heartbeat(self) -> None:
        state = self.wake.state.value if self.wake is not None else self.mode.upper()
        if self.vad is not None:
            peak = self.vad.last_chunk_peak
            rms = self.vad.last_chunk_rms
            audio_depth = self.audio_q.qsize()
        else:
            peak = 0.0
            rms = 0.0
            audio_depth = 0
        print(
            f"[{_ts()}] [.] state={state} backend={self.backend_type.upper()} "
            f"audio_q={audio_depth} asr_q={self.asr_q.qsize()} mic peak={peak:.3f} rms={rms:.3f}"
        )

    def _asr_loop(self) -> None:
        while not self._stop.is_set():
            try:
                item = self.asr_q.get(timeout=0.2)
            except queue.Empty:
                continue
            self._asr_busy.set()
            if self.rust_frontend is not None:
                self.rust_frontend.send_asr_busy()
            try:
                print(f"[{_ts()}] [asr] decoding {item.meta.duration_ms}ms of audio...")
                try:
                    result = self.asr.transcribe(item.audio)
                except Exception as exc:
                    print(f"[{_ts()}] [asr] error: {exc}")
                    continue
                logprob_str = f"{result.avg_logprob:.2f}" if result.avg_logprob != -float("inf") else "-inf"
                print(
                    f"[{_ts()}] [asr] done decode={result.decode_ms}ms "
                    f"text='{result.text}' logprob={logprob_str} "
                    f"no_speech={result.no_speech_prob:.2f} lang={result.language}"
                )
                try:
                    self.result_q.put_nowait(_AsrOutput(audio=item.audio, meta=item.meta, result=result))
                except queue.Full:
                    print(f"[{_ts()}] [pipeline] result_queue full, dropping")
            finally:
                self._asr_busy.clear()
                if self.rust_frontend is not None:
                    self.rust_frontend.send_asr_idle()

    def _poll_python_frontend(self) -> None:
        assert self.vad is not None

        try:
            chunk = self.audio_q.get(timeout=0.1)
        except queue.Empty:
            return

        utterance = self.vad.process(chunk)
        if utterance is None:
            return
        audio, meta = utterance
        if not meta.passed_min_speech:
            self._handle_short_drop(audio, meta)
            return

        if self._asr_busy.is_set() or self.asr_q.qsize() > 0:
            print(
                f"[{_ts()}] [pipeline] BUSY drop dur={meta.duration_ms}ms "
                "(ASR working on prev utterance)"
            )
            return

        try:
            self.asr_q.put_nowait(_PendingUtterance(audio=audio, meta=meta))
            print(f"[{_ts()}] [pipeline] -> asr_queue (depth={self.asr_q.qsize()})")
        except queue.Full:
            print(f"[{_ts()}] [pipeline] asr_queue full, dropping utterance")

    def _poll_rust_frontend(self) -> None:
        assert self.rust_frontend is not None
        try:
            event = self.rust_frontend.events.get(timeout=0.1)
        except queue.Empty:
            return

        if event.kind == "speech_started":
            print(f"[{_ts()}] [vad] speech START rms={int(event.payload.get('rms', 0))}")
            return

        if event.kind == "speech_ended":
            duration_ms = int(event.payload.get("duration_ms", 0))
            peak = float(event.payload.get("peak", 0.0))
            rms = float(event.payload.get("rms", 0.0))
            dropped_short = bool(event.payload.get("dropped_short"))
            dropped_quiet = bool(event.payload.get("dropped_quiet"))
            verdict = "-> ASR"
            if dropped_short:
                verdict = "-> DROP_SHORT"
            elif dropped_quiet:
                verdict = "-> DROP_QUIET"
            print(
                f"[{_ts()}] [vad] speech END   dur={duration_ms}ms "
                f"peak={peak:.3f} rms={rms:.3f}  {verdict}"
            )
            return

        if event.kind == "busy_drop":
            print(
                f"[{_ts()}] [pipeline] BUSY drop dur={int(event.payload.get('duration_ms', 0))}ms "
                "(ASR working on prev utterance)"
            )
            return

        if event.kind == "trace":
            text = str(event.payload.get("message") or "").strip()
            if text:
                print(f"[{_ts()}] [rust] {text}")
            return

        if event.kind == "error":
            print(f"[{_ts()}] [rust] error: {event.payload.get('message', 'unknown error')}")
            return

        if event.kind == "utterance" and event.audio is not None and event.meta is not None:
            try:
                self.asr_q.put_nowait(_PendingUtterance(audio=event.audio, meta=event.meta))
                print(f"[{_ts()}] [pipeline] -> asr_queue (depth={self.asr_q.qsize()})")
            except queue.Full:
                print(f"[{_ts()}] [pipeline] asr_queue full, dropping utterance")

    def _drain_results(self) -> None:
        while True:
            try:
                out = self.result_q.get_nowait()
            except queue.Empty:
                return
            self._handle_utterance(out.audio, out.meta, out.result)

    def _handle_short_drop(self, audio: np.ndarray, meta: UtteranceMeta) -> None:
        sidecar = {
            "timestamp": datetime.now().astimezone().isoformat(),
            "mode": self.mode,
            "label": "drop_tooshort",
            "duration_ms": meta.duration_ms,
            "vad": self._vad_snapshot(meta),
            "asr": None,
            "wake": None,
            "intent": None,
        }
        self.recorder.save(audio, "drop_tooshort", "", sidecar)

    def _handle_utterance(self, audio: np.ndarray, meta: UtteranceMeta, asr: ASRResult) -> None:
        sidecar: dict[str, object] = {
            "timestamp": datetime.now().astimezone().isoformat(),
            "mode": self.mode,
            "duration_ms": meta.duration_ms,
            "vad": self._vad_snapshot(meta),
            "asr": self._asr_snapshot(asr),
            "wake": None,
            "intent": None,
            "smarthome": None,
        }

        transcript = asr.text.strip()
        if self.mode == "transcript":
            print(f"[{_ts()}] [transcript] {transcript or '(empty)'}")
            sidecar["label"] = "transcript"
            self.recorder.save(audio, "transcript", transcript or "silent", sidecar)
            return

        command_text = transcript
        if self.mode == "wake" and self.wake is not None:
            decision = self.wake.decide(transcript, asr.avg_logprob)
            sidecar["wake"] = self._wake_snapshot(decision)
            self._print_wake(decision)
            if not decision.command:
                label = decision.label
                sidecar["label"] = label
                self.recorder.save(audio, label, transcript or "silent", sidecar)
                return
            command_text = decision.command

        confidence = max(0.0, min(1.0, 1.0 - asr.no_speech_prob))
        parsed = parse_intent(command_text, stt_confidence=confidence)
        sidecar["intent"] = self._intent_snapshot(parsed)
        if parsed.normalization_replacements:
            replacement_text = self._format_replacements(parsed.normalization_replacements)
            print(f"[{_ts()}] [normalize] {replacement_text}")

        if not parsed.is_known:
            print(
                f"[{_ts()}] [intent] UNKNOWN conf={parsed.confidence:.2f} "
                f"reason={parsed.reason} normalized='{parsed.normalized_text}'"
            )
            sidecar["label"] = parsed.reason or "unknown_intent"
            self.recorder.save(audio, str(sidecar["label"]), command_text or "silent", sidecar)
            return

        print(
            f"[{_ts()}] [intent] DETECTED intent='{parsed.intent}' conf={parsed.confidence:.2f} "
            f"alias='{parsed.matched_alias}' normalized='{parsed.normalized_text}'"
        )
        if parsed.payload:
            print(
                f"[{_ts()}] [intent] payload={json.dumps(parsed.payload, ensure_ascii=False, sort_keys=True)}"
            )

        sidecar["label"] = parsed.intent
        if parsed.intent.startswith("smarthome."):
            try:
                command = build_smart_home_command(parsed.intent, payload=parsed.payload)
            except Exception as exc:
                print(f"[{_ts()}] [smarthome] payload build failed: {exc}")
                sidecar["smarthome"] = {"error": str(exc)}
            else:
                sidecar["smarthome"] = {
                    "device_key": command.device_key,
                    "device_id": command.device_id,
                    "action": command.action,
                    "content": command.content,
                    "display_name": command.display_name,
                    "action_label": command.action_label,
                }
                print(
                    f"[{_ts()}] [smarthome] dry-run target=/device/control payload='{command.content}'"
                )

        self.recorder.save(audio, parsed.intent, command_text or "silent", sidecar)

    def _print_wake(self, decision: WakeDecision) -> None:
        parts: list[str] = []
        if decision.matched_alias is not None:
            parts.append(f"matched='{decision.matched_alias}' edit={decision.edit_distance}")
        if decision.command:
            parts.append(f"cmd='{decision.command}'")
        extra = ("  " + "  ".join(parts)) if parts else ""
        print(
            f"[{_ts()}] [wake] {decision.label.upper():<11} "
            f"{decision.state_before}->{decision.state_after}{extra}"
        )

    def _vad_snapshot(self, meta: UtteranceMeta) -> dict[str, object]:
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

    def _asr_snapshot(self, result: ASRResult) -> dict[str, object]:
        return {
            "model": self.asr_cfg.model,
            "language": result.language,
            "text": result.text,
            "avg_logprob": round(result.avg_logprob, 3) if result.avg_logprob != -float("inf") else None,
            "no_speech_prob": round(result.no_speech_prob, 3),
            "compression_ratio": round(result.compression_ratio, 3),
            "decode_ms": result.decode_ms,
        }

    def _wake_snapshot(self, decision: WakeDecision) -> dict[str, object]:
        return {
            "label": decision.label,
            "matched_alias": decision.matched_alias,
            "edit_distance": decision.edit_distance,
            "command": decision.command,
            "state_before": decision.state_before,
            "state_after": decision.state_after,
        }

    def _intent_snapshot(self, parsed: IntentParseResult) -> dict[str, object]:
        return {
            "intent": parsed.intent,
            "confidence": round(parsed.confidence, 3),
            "text": parsed.text,
            "normalized_text": parsed.normalized_text,
            "matched_alias": parsed.matched_alias,
            "reason": parsed.reason,
            "payload": parsed.payload,
            "normalization_replacements": parsed.normalization_replacements,
        }

    @staticmethod
    def _format_replacements(replacements: list[dict[str, object]]) -> str:
        chunks: list[str] = []
        for item in replacements:
            before = item.get("from")
            after = item.get("to")
            mode = item.get("mode")
            chunks.append(f"{before}->{after} ({mode})")
        return ", ".join(chunks)
