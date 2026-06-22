SLSA 建置來源證明(Provenance)
==============================

框架能簽署動作檔(HMAC)並盤點相依套件(SBOM),但無法證明*哪個建置產生了什麼* —— 也就是把產物
摘要綁定到建置中繼資料的 SLSA 來源證明。本功能補上一個 in-toto v1 Statement,攜帶覆蓋檔案
``sha256`` 摘要的 SLSA v1 provenance predicate,並附上會重新雜湊產物的驗證器。

純標準函式庫(``hashlib`` + ``json``);完全離線;不匯入 ``PySide6``。Statement 的 DSSE 簽署留作
選用的後續層。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        subject_for, build_provenance, write_provenance, verify_provenance)

    subjects = [subject_for("dist/app.whl"), subject_for("sbom.cdx.json")]
    statement = build_provenance(
        subjects, builder_id="github-actions",
        metadata={"invocation_id": "run-42", "started_on": "2026-06-21T00:00:00Z"})
    write_provenance(statement, "app.intoto.jsonl")

    # 之後,在消費端
    mismatches = verify_provenance(statement, {"app.whl": "dist/app.whl"})
    if not mismatches:
        print("產物摘要已驗證")

``subject_for`` 把檔案雜湊成 in-toto subject(``subject_for_bytes`` 對記憶體資料做同樣的事);
``build_provenance`` 把 subjects 包進 in-toto v1 / SLSA v1 信封(``buildDefinition`` +
``runDetails``);``verify_provenance`` 重新雜湊每個具名檔案並回傳任何摘要不符。它與
``action_signing``(簽署動作 JSON)及 ``sbom``(盤點相依套件)互補 —— 可一併證明 SBOM 與已簽署的
產物。

執行器命令
----------

``AC_build_provenance`` 接受 ``paths``(清單或 JSON 字串)及選用的 ``builder_id`` /
``build_type``,回傳 ``{statement}``。``AC_verify_provenance`` 接受 ``statement`` 與 ``files``
(name->path),回傳 ``{ok, mismatches}``。兩者皆以 MCP 工具(``ac_build_provenance`` /
``ac_verify_provenance``)以及 Script Builder 中 **Security** 分類下的命令提供。
