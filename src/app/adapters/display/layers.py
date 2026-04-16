"""T-016: Display layer system.

PRD 3-layer UI: Core Face, Action Overlay, System HUD.
각 레이어를 독립적으로 업데이트하고 합성하는 layer compositor.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class LayerType(Enum):
    CORE_FACE = "core_face"
    ACTION_OVERLAY = "action_overlay"
    SYSTEM_HUD = "system_hud"


@dataclass
class LayerContent:
    """한 레이어의 렌더링 콘텐츠."""
    expression: str = "neutral"          # 표정 이름 (Core Face)
    overlay_type: Optional[str] = None   # 오버레이 종류 (Action Overlay)
    hud_items: List[Dict[str, Any]] = field(default_factory=list)  # HUD 요소들
    opacity: float = 1.0
    visible: bool = True
    extra: Dict[str, Any] = field(default_factory=dict)


class Layer:
    """단일 레이어."""

    def __init__(self, layer_type: LayerType) -> None:
        self.layer_type = layer_type
        self.content = LayerContent()
        self._dirty = True

    def update(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            if hasattr(self.content, key):
                setattr(self.content, key, value)
        self._dirty = True

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def mark_clean(self) -> None:
        self._dirty = False


class LayerStack:
    """3-layer compositor."""

    def __init__(self) -> None:
        self.core_face = Layer(LayerType.CORE_FACE)
        self.action_overlay = Layer(LayerType.ACTION_OVERLAY)
        self.system_hud = Layer(LayerType.SYSTEM_HUD)
        self._layers = [self.core_face, self.action_overlay, self.system_hud]

    def get_layer(self, layer_type: LayerType) -> Layer:
        for layer in self._layers:
            if layer.layer_type == layer_type:
                return layer
        raise ValueError(f"Unknown layer: {layer_type}")

    def any_dirty(self) -> bool:
        return any(l.is_dirty for l in self._layers)

    def compose(self) -> Dict[str, LayerContent]:
        """모든 레이어 합성 결과를 반환."""
        result = {}
        for layer in self._layers:
            if layer.content.visible:
                result[layer.layer_type.value] = layer.content
            layer.mark_clean()
        return result

    def set_expression(self, expression: str) -> None:
        """Core Face 표정 변경."""
        self.core_face.update(expression=expression)

    def set_overlay(self, overlay_type: Optional[str], **extra: Any) -> None:
        """Action Overlay 설정."""
        self.action_overlay.update(
            overlay_type=overlay_type,
            visible=overlay_type is not None,
            extra=extra,
        )

    def set_hud_items(self, items: List[Dict[str, Any]]) -> None:
        """System HUD 아이템 갱신."""
        self.system_hud.update(hud_items=items)

    def set_dim(self, dim: bool) -> None:
        """Away 모드 dimming."""
        self.core_face.update(opacity=0.3 if dim else 1.0)
