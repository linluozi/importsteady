"""Per-module import self-time recorder.

The hook sits at the front of ``sys.meta_path`` and wraps the concrete loader
returned by ``PathFinder``.  Timing is stack based: a module's self time is its
total ``exec_module`` duration minus the total duration of every module executed
inside it.  That keeps parent packages from absorbing their children's cost and,
unlike ``python -X importtime``, does not attribute interpreter shutdown or
trace flushing to the root module.

Overhead is two ``perf_counter_ns`` calls per executed module (a few us).
"""

from __future__ import annotations

import sys
import time
from importlib.abc import MetaPathFinder
from importlib.machinery import PathFinder

_records: dict[str, list[int]] = {}
_stack: list[list[int | str]] = []
_installed = False


def _enter(name: str) -> None:
    _stack.append([name, time.perf_counter_ns(), 0])


def _exit() -> None:
    name, start, child_ns = _stack.pop()
    elapsed = time.perf_counter_ns() - int(start)
    self_ns = elapsed - int(child_ns)
    _records.setdefault(str(name), []).append(max(self_ns, 0))
    if _stack:
        _stack[-1][2] = int(_stack[-1][2]) + elapsed


class _TimingLoader:
    """Delegating loader that times ``exec_module`` only."""

    def __init__(self, loader):
        self._loader = loader

    def create_module(self, spec):
        return self._loader.create_module(spec)

    def exec_module(self, module):
        _enter(module.__name__)
        try:
            return self._loader.exec_module(module)
        finally:
            _exit()

    def __getattr__(self, attr):
        return getattr(self._loader, attr)


class _TimingFinder(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        spec = PathFinder.find_spec(fullname, path, target)
        if (
            spec is not None
            and spec.loader is not None
            and not isinstance(spec.loader, _TimingLoader)
        ):
            spec.loader = _TimingLoader(spec.loader)
        return spec


def install() -> None:
    global _installed
    if _installed:
        return
    sys.meta_path.insert(0, _TimingFinder())
    _installed = True


def reset() -> None:
    _records.clear()
    _stack.clear()


def take() -> dict[str, int]:
    """Return summed self time in ns per module and clear the buffer."""
    out = {name: sum(values) for name, values in _records.items()}
    reset()
    return out
