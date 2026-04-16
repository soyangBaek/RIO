"""Smart-home flow integration."""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from app.core.events import topics  # noqa: E402
from app.domains.smart_home import SmartHomeService  # noqa: E402


class FakeClient:
    def __init__(self, ok=True, status=200, error=None):
        self._r = {"ok": ok, "status": status, "error": error}
    def send_command(self, body):
        self.last_body = body
        return self._r


def test_smarthome_success_emits_result_and_task_succeeded():
    emitted = []
    svc = SmartHomeService(
        publish=emitted.append,
        client=FakeClient(ok=True),
        devices={"aircon": "거실 에어컨"},
    )
    svc.start({"payload": {"intent": "smarthome.aircon.on"}, "trace_id": "tr1"})
    time.sleep(0.1)

    sent = [e for e in emitted if e.topic == topics.SMARTHOME_REQUEST_SENT]
    result = [e for e in emitted if e.topic == topics.SMARTHOME_RESULT]
    succeeded = [e for e in emitted if e.topic == topics.TASK_SUCCEEDED]
    assert sent[0].payload["content"] == "거실 에어컨 켜줘"
    assert result[0].payload["ok"] is True
    assert len(succeeded) == 1


def test_smarthome_failure_propagates_error():
    emitted = []
    svc = SmartHomeService(
        publish=emitted.append,
        client=FakeClient(ok=False, status=500, error="timeout"),
    )
    svc.start({"payload": {"intent": "smarthome.light.on"}, "trace_id": "tr2"})
    time.sleep(0.1)

    failed = [e for e in emitted if e.topic == topics.TASK_FAILED]
    assert len(failed) == 1 and failed[0].payload["error"] == "timeout"


def test_smarthome_unknown_intent_fails_immediately():
    emitted = []
    svc = SmartHomeService(publish=emitted.append, client=FakeClient())
    svc.start({"payload": {"intent": "bogus"}, "trace_id": "tr3"})
    assert emitted[-1].topic == topics.TASK_FAILED
    assert emitted[-1].payload["error"] == "unknown_intent"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
