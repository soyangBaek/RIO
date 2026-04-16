"""Minimal pyplot stub.

MediaPipe imports `matplotlib.pyplot` in drawing utilities even when we only
use face/hands solutions. For this project we don't call the 3D plotting
helpers, so a tiny no-op implementation is enough.
"""


class _DummyAxes:
    def __getattr__(self, name):
        def _noop(*args, **kwargs):
            return None

        return _noop


def figure(*args, **kwargs):
    return None


def axes(*args, **kwargs):
    return _DummyAxes()


def show(*args, **kwargs):
    return None
