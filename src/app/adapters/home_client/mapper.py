"""Intent-to-home-client request mapper.

Thin wrapper over :mod:`app.domains.smart_home.payloads` kept in the
adapter layer so the transport-level adapter does not import domain code
directly. The domain service computes the content string; this mapper
assembles the final HTTP body and adds any adapter-owned fields (trace id
echo, correlation id) that the home-client API may want.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from ...domains.smart_home.payloads import build_content


def intent_to_body(
    intent_id: str,
    devices: Optional[Dict[str, str]] = None,
    trace_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    content = build_content(intent_id, devices)
    if content is None:
        return None
    body: Dict[str, Any] = {"content": content}
    if trace_id:
        body["trace_id"] = trace_id
    return body
