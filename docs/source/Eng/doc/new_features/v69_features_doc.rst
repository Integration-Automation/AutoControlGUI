SLSA Build Provenance
=====================

The framework can sign action files (HMAC) and inventory dependencies (SBOM),
but it could not attest *what was produced by which build* — the SLSA
provenance attestation that binds artifact digests to build metadata. This adds
an in-toto v1 Statement carrying a SLSA v1 provenance predicate over file
``sha256`` digests, plus a verifier that re-hashes the artifacts.

Pure standard library (``hashlib`` + ``json``); fully offline; imports no
``PySide6``. DSSE signing of the statement is left as an optional later layer.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        subject_for, build_provenance, write_provenance, verify_provenance)

    subjects = [subject_for("dist/app.whl"), subject_for("sbom.cdx.json")]
    statement = build_provenance(
        subjects, builder_id="github-actions",
        metadata={"invocation_id": "run-42", "started_on": "2026-06-21T00:00:00Z"})
    write_provenance(statement, "app.intoto.jsonl")

    # later, on the consumer side
    mismatches = verify_provenance(statement, {"app.whl": "dist/app.whl"})
    if not mismatches:
        print("artifact digests verified")

``subject_for`` hashes a file into an in-toto subject (``subject_for_bytes``
does the same for in-memory data); ``build_provenance`` wraps the subjects in
the in-toto v1 / SLSA v1 envelope (``buildDefinition`` + ``runDetails``);
``verify_provenance`` re-hashes each named file and returns any digest
mismatch. It complements ``action_signing`` (which signs action JSON) and
``sbom`` (which inventories dependencies) — attest the SBOM and signed
artifacts together.

Executor commands
-----------------

``AC_build_provenance`` takes ``paths`` (a list, or JSON string) plus optional
``builder_id`` / ``build_type`` and returns ``{statement}``.
``AC_verify_provenance`` takes a ``statement`` and ``files`` (name->path) and
returns ``{ok, mismatches}``. Both are exposed as MCP tools
(``ac_build_provenance`` / ``ac_verify_provenance``) and as Script Builder
commands under **Security**.
