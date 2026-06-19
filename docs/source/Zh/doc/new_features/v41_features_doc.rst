S3 相容成品儲存
===============

一次執行產生的報告、螢幕截圖與螢幕錄影,通常值得存放到 runner 之外。
``S3ArtifactStore`` 可對任何 S3 相容儲存桶(AWS S3、MinIO、Cloudflare R2…)上傳、下
載、列出與刪除這些成品。

``boto3`` 為**選用**相依(``pip install je_auto_control[s3]``):S3 client *可注入*,因
此儲存體的邏輯可用假 client 完整單元測試,且僅在未提供 client 時才匯入 ``boto3``。整個
API 皆相對於儲存體設定的 ``prefix`` —— ``upload`` 回傳儲存體相對鍵,``download`` /
``delete`` / ``url`` 原樣接受,而 ``list`` 則會把 prefix 去除。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import S3ArtifactStore

    store = S3ArtifactStore("my-bucket", prefix="runs/42")   # boto3 client 延遲建立
    key = store.upload("report.html")          # -> "report.html"(相對)
    store.url(key)                             # -> "s3://my-bucket/runs/42/report.html"
    store.download(key, "local/report.html")
    store.list()                              # -> ["report.html", ...]
    store.delete(key)

測試或非 AWS 後端可傳入自己的 client:``S3ArtifactStore("bucket", client=my_client)``。

.. note::

   實際的 AWS 路徑需要 ``boto3`` 與憑證,因此不會在 CI 中執行;儲存體邏輯以假 S3
   client 驗證。

執行器指令
----------

模組層級的預設儲存體 —— 以 ``configure_default_store(bucket, client=None, prefix="")``
設定一次 —— 支撐 executor/MCP 指令:

================================ ===================================================
指令                             效果
================================ ===================================================
``AC_s3_upload``                 上傳本機成品;回傳 ``{key}``。
``AC_s3_download``               將物件下載到本機路徑。
``AC_s3_list``                   列出物件鍵(可加 ``prefix``)。
``AC_s3_delete``                 刪除物件。
================================ ===================================================

相同操作亦提供為 MCP 工具(``ac_s3_upload`` / ``ac_s3_download`` / ``ac_s3_list`` /
``ac_s3_delete``),以及 Script Builder 中 **Tools** 分類下的指令。
