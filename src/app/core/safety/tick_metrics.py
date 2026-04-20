"""이벤트 루프 tick 별 소요 시간 기록 + 주기적 요약.

§1.D v1 범위: run_rio_app.py 의 외부 루프 지표만 수집.
- pump_ms: pump_workers() 소요
- drain_ms: drain_bus() 소요
- preview_ms: PreviewWindow.update() 소요 (프리뷰 on 일 때만)

ASR decode ms / frame loop ms / face detect ms 같은 내부 계측은 별도 후속.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from typing import Iterable


_LOGGER = logging.getLogger("rio.metrics")


class TickMetrics:
    """Rolling tick 지표. 최근 window 개 샘플에 대해 avg/p95/max 를 뽑는다.

    사용 예::

        metrics = TickMetrics(window=256, interval_s=5.0)
        while True:
            t0 = time.monotonic()
            rio.pump_workers()
            metrics.record("pump_ms", (time.monotonic() - t0) * 1000)
            metrics.maybe_log()
    """

    def __init__(self, *, window: int = 256, interval_s: float = 5.0) -> None:
        self._window = max(8, int(window))
        self._interval_s = float(interval_s)
        self._buffers: dict[str, deque[float]] = {}
        self._counters: dict[str, int] = {}
        self._total_ticks = 0
        self._last_log_at: float | None = None

    def record(self, phase: str, elapsed_ms: float) -> None:
        buffer = self._buffers.get(phase)
        if buffer is None:
            buffer = deque(maxlen=self._window)
            self._buffers[phase] = buffer
        buffer.append(float(elapsed_ms))

    def increment(self, name: str, by: int = 1) -> None:
        self._counters[name] = self._counters.get(name, 0) + int(by)

    def tick_done(self) -> None:
        self._total_ticks += 1

    @property
    def total_ticks(self) -> int:
        return self._total_ticks

    def counters(self) -> dict[str, int]:
        return dict(self._counters)

    def snapshot(self) -> dict[str, dict[str, float]]:
        result: dict[str, dict[str, float]] = {}
        for phase, buffer in self._buffers.items():
            if not buffer:
                continue
            result[phase] = _summarize(buffer)
        return result

    def format_summary(self) -> str:
        stats = self.snapshot()
        parts = [f"ticks={self._total_ticks}"]
        if not stats and not self._counters:
            parts.append("(no samples)")
            return " ".join(parts)
        for phase in sorted(stats):
            s = stats[phase]
            parts.append(
                f"{phase} avg={s['avg']:.2f}ms p95={s['p95']:.2f}ms max={s['max']:.2f}ms n={int(s['n'])}"
            )
        for name in sorted(self._counters):
            parts.append(f"{name}={self._counters[name]}")
        return " ".join(parts)

    def maybe_log(self, *, now: float | None = None, logger: logging.Logger | None = None) -> bool:
        if self._interval_s <= 0:
            return False
        current = now if now is not None else time.monotonic()
        if self._last_log_at is None:
            self._last_log_at = current
            return False
        if current - self._last_log_at < self._interval_s:
            return False
        target = logger or _LOGGER
        target.info("[metrics] %s", self.format_summary())
        self._last_log_at = current
        return True


def _summarize(samples: Iterable[float]) -> dict[str, float]:
    data = sorted(samples)
    n = len(data)
    total = sum(data)
    avg = total / n
    p95_idx = min(n - 1, max(0, int(round(0.95 * (n - 1)))))
    return {
        "avg": avg,
        "p95": data[p95_idx],
        "max": data[-1],
        "n": float(n),
    }


# ── 공유 accessor ──────────────────────────────────────────────────
#
# adapter 가 "orchestrator 인스턴스 없이" 계측하도록, 프로세스 단위 단일
# TickMetrics 를 전역으로 노출한다. set 되어 있지 않으면 get_active_metrics()
# 는 None 을 돌려주고 adapter 측은 조용히 no-op 한다.

_ACTIVE: TickMetrics | None = None


def get_active_metrics() -> TickMetrics | None:
    return _ACTIVE


def set_active_metrics(metrics: TickMetrics | None) -> None:
    global _ACTIVE
    _ACTIVE = metrics


def record(phase: str, elapsed_ms: float) -> None:
    m = _ACTIVE
    if m is not None:
        m.record(phase, elapsed_ms)


def increment(name: str, by: int = 1) -> None:
    m = _ACTIVE
    if m is not None:
        m.increment(name, by)


__all__ = [
    "TickMetrics",
    "get_active_metrics",
    "set_active_metrics",
    "record",
    "increment",
]
