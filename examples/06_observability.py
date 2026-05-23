"""Expose Prometheus /metrics and add a span around user code.

Start this script and curl ``http://127.0.0.1:9090/metrics`` to see the
built-in executor + agent metrics plus the custom counter below.

For real production: stand up Prometheus with a scrape job pointing at
this URL, then a Grafana dashboard. Add ``opentelemetry-api`` to the
environment and the no-op tracer auto-upgrades to real OTel spans.
"""
import urllib.request

import je_auto_control as ac


def main() -> None:
    exporter = ac.default_metrics_exporter()
    exporter.start()
    print(f"metrics exposed at http://127.0.0.1:{exporter.port}/metrics")

    registry = ac.default_metric_registry()
    custom_counter = registry.register(ac.MetricCounter(
        "myapp_pipeline_runs_total",
        "Number of times this example pipeline ran.",
        label_names=("outcome",),
    ))

    @ac.traced("example.do_work")
    def do_work() -> None:
        custom_counter.inc(labels={"outcome": "ok"})

    for _ in range(3):
        do_work()

    # Self-scrape to show the resulting Prometheus text.
    with urllib.request.urlopen(
            f"http://127.0.0.1:{exporter.port}/metrics", timeout=2.0,
    ) as resp:
        text = resp.read().decode("utf-8")

    print()
    print("/metrics says:")
    print(text)

    exporter.stop()


if __name__ == "__main__":
    main()
