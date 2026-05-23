================================
可觀測性 — Metrics 與 Traces
================================

AutoControl 內建 Prometheus 相容的 ``/metrics`` 端點，
以及 OpenTelemetry 風格的 tracer。即裝即用就能拿到：

- 每個動作的呼叫次數與延遲分布（histogram）。
- 每一步 agent loop 的計數，按工具名稱與成功／失敗分桶。
- 在 executor、agent loop 內外，加上任何用 :func:`traced` 包起來
  的使用者函式的 span 樹。

Metric 基礎元件只用標準函式庫實作，所以**不需要**事先安裝
``prometheus_client``。之後若你裝了 ``prometheus_client`` 或
``opentelemetry-api``，AutoControl 會自動偵測並改走 SDK。

.. contents::
   :local:
   :depth: 2

快速開始
========

啟動內建的 HTTP exporter，讓 scrape job 抓得到::

   from je_auto_control import default_metrics_exporter

   exporter = default_metrics_exporter()  # 預設綁定 127.0.0.1:9090
   exporter.start()

另一邊::

   $ curl http://127.0.0.1:9090/metrics
   # HELP autocontrol_action_calls_total Number of AC_* actions executed
   # TYPE autocontrol_action_calls_total counter
   autocontrol_action_calls_total{action="AC_screenshot",outcome="ok"} 42
   ...

把這個 URL 加進 Prometheus 設定，Grafana dashboard 就有東西看了。

內建 metrics
============

下列 metric 由 executor 與 agent loop 自動發送，\ **不需要**\ 寫任何
instrumentation：

================================================  =========  =======================================
Metric                                            Type       Labels
================================================  =========  =======================================
``autocontrol_action_calls_total``                Counter    ``action``、``outcome``（``ok``/``error``）
``autocontrol_action_duration_seconds``           Histogram  ``action``
``autocontrol_agent_runs_total``                  Counter    *(無)*
``autocontrol_agent_steps_total``                 Counter    ``tool``、``outcome``
``autocontrol_agent_outcomes_total``              Counter    ``outcome``（``succeeded``/``failed``）
================================================  =========  =======================================

Histogram 使用 Prometheus 預設的桶配置（5 ms → 10 s），同步按鍵到
緩慢的 OCR 都涵蓋得到。

自訂 metrics
============

同一組原語也透過套件 facade 對外::

   from je_auto_control import (
       MetricCounter, MetricGauge, MetricHistogram, default_metric_registry,
   )

   registry = default_metric_registry()
   widgets_built = registry.register(MetricCounter(
       "myapp_widgets_built_total",
       "我這條 pipeline 產生的 widget 數量。",
       label_names=("kind",),
   ))

   widgets_built.inc(labels={"kind": "blue"})

名稱遵守 Prometheus 規則：snake_case、不可有 dash、開頭必須是字母或
底線。Registry 偵測到同名衝突會丟例外，避免拼錯字默默分裂出新 series。

Tracing
=======

:func:`traced` decorator 會用一個 span 包住任何 callable。預設 tracer
在 ``opentelemetry-api`` 沒裝時是 no-op；裝上之後 span 會自動透過你
設定的 exporter 流出（OTLP、Jaeger、Datadog……），\ **不需要**\ 修改
呼叫端::

   from je_auto_control import traced

   @traced("my_pipeline.process_one")
   def process_one(item):
       ...

需要手動控制 span 時::

   from je_auto_control import default_tracer

   tracer = default_tracer()
   with tracer.start_as_current_span("crop_and_ocr") as span:
       span.set_attribute("region", "header")
       ...

正式部署建議
============

多台 AutoControl daemon 的部署典型做法：

1. 每台主機開機時呼叫 ``default_metrics_exporter().start()``。
2. Prometheus 每 15 秒 scrape ``host:9090/metrics``。
3. 安裝 ``opentelemetry-api`` + ``opentelemetry-sdk`` + 你選的 OTLP
   exporter（Datadog／Honeycomb／Jaeger）。
4. 在 Grafana 設警報：

   - ``rate(autocontrol_action_calls_total{outcome="error"}[5m]) > 0.1``
   - ``histogram_quantile(0.99, rate(autocontrol_action_duration_seconds_bucket[5m])) > 2.0``
   - ``up{job="autocontrol"} == 0``

Exporter 預設綁定 ``127.0.0.1``。要對外開放給 scrape，請傳
``host="0.0.0.0"`` \ **並且**\ 放在防火牆或反向代理後面 —— ``/metrics``
本身沒有身份驗證。

安全提醒
========

Metrics 只記錄動作名稱，不包含 payload，所以 ``/metrics`` 外洩風險不
高。Trace span 可能會帶上 agent goal 與工具參數的前 120 字元；若要把
trace 送到第三方 SaaS，請先確認 :func:`traced` 呼叫站的安全性。
