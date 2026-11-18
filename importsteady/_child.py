"""Child process entry point: import one target and emit timings as JSON."""

from __future__ import annotations

import importlib
import platform
import sys
import time

from importsteady import _hook


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("usage: python -m importsteady._child <module>", file=sys.stderr)
        return 2

    target = argv[0]
    if target in sys.modules:
        import json

        json.dump(
            {
                "target": target,
                "error": "target is already imported by interpreter startup; "
                "pick a module that is not loaded before user code",
            },
            sys.stdout,
        )
        sys.stdout.write("\n")
        return 1
    _hook.install()
    _hook.reset()
    start = time.perf_counter_ns()
    try:
        importlib.import_module(target)
    except Exception as exc:  # report, never swallow
        import json

        json.dump(
            {"target": target, "error": f"{type(exc).__name__}: {exc}"},
            sys.stdout,
        )
        sys.stdout.write("\n")
        return 1
    total_ns = time.perf_counter_ns() - start
    self_ns = _hook.take()
    import json  # imported after the measurement so the target is unaffected

    json.dump(
        {
            "target": target,
            "python": platform.python_version(),
            "total_ns": total_ns,
            "self_ns": self_ns,
        },
        sys.stdout,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
