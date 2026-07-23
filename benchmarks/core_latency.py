"""Repeatable smoke benchmark for stable headless entry points."""
import json
import statistics
import time


def _measure(callable_, repeats=20):
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        callable_()
        samples.append((time.perf_counter() - start) * 1000)
    ordered = sorted(samples)
    return {
        "median_ms": round(statistics.median(samples), 3),
        "p95_ms": round(ordered[max(0, int(len(ordered) * .95) - 1)], 3),
    }


def main():
    import je_auto_control.api as ac
    results = {
        "diagnostics_ms": _measure(ac.run_diagnostics, repeats=5),
        "codegen_ms": _measure(
            lambda: ac.generate_code([["AC_screen_size"]]), repeats=20),
    }
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
