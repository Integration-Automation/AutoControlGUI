S3-Compatible Artifact Store
============================

Reports, screenshots, and screen recordings produced by a run are usually worth
keeping off the runner. ``S3ArtifactStore`` uploads, downloads, lists, and
deletes them against any S3-compatible bucket (AWS S3, MinIO, Cloudflare R2, …).

``boto3`` is an **optional** dependency (``pip install je_auto_control[s3]``):
the S3 client is *injectable*, so the store's logic is fully unit-testable with a
fake client and ``boto3`` is imported only when no client is supplied. The whole
API is relative to the store's configured ``prefix`` — ``upload`` returns a
store-relative key that ``download`` / ``delete`` / ``url`` accept unchanged, and
``list`` strips the prefix back off. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import S3ArtifactStore

    store = S3ArtifactStore("my-bucket", prefix="runs/42")   # boto3 client lazily built
    key = store.upload("report.html")          # -> "report.html"  (relative)
    store.url(key)                             # -> "s3://my-bucket/runs/42/report.html"
    store.download(key, "local/report.html")
    store.list()                              # -> ["report.html", ...]
    store.delete(key)

For tests or non-AWS backends, pass your own client:
``S3ArtifactStore("bucket", client=my_client)``.

.. note::

   The live AWS path requires ``boto3`` plus credentials and is therefore not
   exercised in CI; the store's logic is validated against a fake S3 client.

Executor commands
-----------------

A module-level default store — configured once with
``configure_default_store(bucket, client=None, prefix="")`` — backs the
executor/MCP commands:

================================ ===================================================
Command                          Effect
================================ ===================================================
``AC_s3_upload``                 Upload a local artifact; returns ``{key}``.
``AC_s3_download``               Download an object to a local path.
``AC_s3_list``                   List object keys (optional extra ``prefix``).
``AC_s3_delete``                 Delete an object.
================================ ===================================================

The same operations are exposed as MCP tools (``ac_s3_upload`` /
``ac_s3_download`` / ``ac_s3_list`` / ``ac_s3_delete``) and as Script Builder
commands under **Tools**.
