# Offline journal candidate example

```powershell
python -m je_auto_control.cli codegen --from-log benchmarks/journal_codegen/actions.jsonl --run-id demo -o .test-tmp/test_observed.py
```

This synthetic schema-one fixture describes two completed `AC_sleep` children
under a loop. Generation reads and validates it without sleeping or driving a
device. Review the source, `.manifest.json` and `.actions.json` before execution.
The candidate serializes only observed children; it does not reconstruct the
loop, unobserved branches, retry policy or parallel timing. Warnings and all
parent/step/source identities remain in the manifest/artifact.

Without `-o`, CLI writes candidate source to stdout and warnings to stderr.
`--target`, `--style`, `--name` and `--failure-bundle` keep the existing rendering
options. Journal mode defaults to `actions`; ordinary action-file mode retains
`calls`. For a structured in-memory artifact use `api.codegen.generate_journal_candidate`.
Generated Python passes AST validation; all targets pass command/argument and
pure executor dry-run validation. Generation never imports or runs the result.
