"""마이크 캡처: sounddevice(PortAudio) → queue.Queue[float32 mono chunks]."""
from __future__ import annotations

import queue
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
import sounddevice as sd


def _ts() -> str:
    t = time.time()
    return time.strftime("%H:%M:%S", time.localtime(t)) + f".{int((t - int(t)) * 1000):03d}"


# ── pactl 기반 mic 게인 유틸 ─────────────────────────────────

def _run_pactl(args: list[str]) -> tuple[int, str, str]:
    if shutil.which("pactl") is None:
        return -1, "", "pactl not found"
    try:
        r = subprocess.run(["pactl", *args], capture_output=True, text=True, timeout=3)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return -2, "", "pactl timeout"


def _get_default_source() -> Optional[str]:
    code, out, _ = _run_pactl(["info"])
    if code != 0:
        return None
    for line in out.splitlines():
        if line.startswith("Default Source:"):
            return line.split(":", 1)[1].strip()
    return None


def _find_source_by_hint(hint: str) -> Optional[str]:
    """실제 입력 장치 우선(`alsa_input.*`), 그 다음 fallback 으로 다른 매치.

    헤드셋/스피커 장치는 출력 monitor source(`alsa_output.*.monitor`)도 같이 만들어지기 때문에
    hint 가 둘 다 매치하는 경우 monitor 가 먼저 잡히는 오작동 방지.
    """
    code, out, _ = _run_pactl(["list", "short", "sources"])
    if code != 0:
        return None
    fallback: Optional[str] = None
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        name = parts[1]
        if hint not in name:
            continue
        if name.startswith("alsa_input."):
            return name
        if fallback is None:
            fallback = name
    return fallback


def apply_mic_gain(percent: int, source_hint: Optional[str] = None) -> None:
    """pactl 로 mic 게인을 percent % 로 설정. 실패해도 예외는 던지지 않고 로그만 남김."""
    source = _find_source_by_hint(source_hint) if source_hint else _get_default_source()
    if source is None:
        print(f"[{_ts()}] [audio] mic gain: source not found "
              f"(hint={source_hint!r}) — leaving volume unchanged")
        return

    code, _out, err = _run_pactl(["set-source-volume", source, f"{percent}%"])
    if code != 0:
        print(f"[{_ts()}] [audio] mic gain set FAILED on '{source}': {err}")
        return

    _, vol_out, _ = _run_pactl(["get-source-volume", source])
    summary = vol_out.splitlines()[0] if vol_out else ""
    print(f"[{_ts()}] [audio] mic gain → {percent}% on '{source}'"
          + (f"  | {summary}" if summary else ""))


@dataclass
class AudioConfig:
    device: Optional[str]
    sample_rate: int
    channels: int
    blocksize: int
    dtype: str


def list_devices() -> str:
    return str(sd.query_devices())


def resolve_device(device_hint: Optional[str]) -> Optional[int | str]:
    """부분일치로 input 장치 인덱스를 찾고, 못 찾으면 원본 문자열 그대로 반환.

    - None        → None (PortAudio 기본 입력)
    - 문자열 매치  → 장치 인덱스 (int)
    - 매치 실패   → 원본 문자열 (PortAudio가 이름 문자열도 허용)
    """
    if device_hint is None:
        return None
    try:
        devices = sd.query_devices()
    except Exception:
        return device_hint
    for idx, dev in enumerate(devices):
        if device_hint in dev["name"] and dev["max_input_channels"] > 0:
            return idx
    return device_hint


class AudioSource:
    """sounddevice InputStream 을 열고 콜백에서 큐로 float32 mono 청크를 푸시."""

    def __init__(self, cfg: AudioConfig, audio_queue: "queue.Queue[np.ndarray]"):
        self.cfg = cfg
        self.queue = audio_queue
        self.stream: Optional[sd.InputStream] = None

    def _callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        if status:
            print(f"[{_ts()}] [audio] status: {status}")
        # indata shape: (frames, channels). channels=1 이면 (frames, 1).
        mono = indata[:, 0].astype(np.float32, copy=True)
        try:
            self.queue.put_nowait(mono)
        except queue.Full:
            # 소비자가 느려져서 버퍼가 찼을 때. 경고만 남기고 drop (실시간성 우선).
            print(f"[{_ts()}] [audio] queue full, dropping chunk")

    def start(self) -> None:
        device = resolve_device(self.cfg.device)
        print(f"[{_ts()}] [audio] opening device={device!r} rate={self.cfg.sample_rate} "
              f"blocksize={self.cfg.blocksize} ch={self.cfg.channels} dtype={self.cfg.dtype}")
        self.stream = sd.InputStream(
            samplerate=self.cfg.sample_rate,
            channels=self.cfg.channels,
            blocksize=self.cfg.blocksize,
            dtype=self.cfg.dtype,
            device=device,
            callback=self._callback,
        )
        self.stream.start()

    def stop(self) -> None:
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None
