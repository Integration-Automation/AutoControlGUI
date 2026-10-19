Journal-to-code candidates
==========================

Generate a reviewable Python, pytest or Robot candidate from one explicitly
selected structured action-journal run. Generation never replays an action,
captures a screen or calls a model. A successful static check is separate from
native operation success and external dependency availability.

Python API
----------

The experimental API returns ``CandidateScript`` with ``code``, ``actions``,
``manifest``, ``warnings`` and ``observed_path_only``. An independent JSON review
bundle is available through ``to_dict()``::

    from pathlib import Path
    from je_auto_control import generate_candidate_from_log, write_candidate_archive

    candidate = generate_candidate_from_log(
        Path("run.jsonl"), run_id="selected-run",
        target="pytest", style="actions",
    )
    print(candidate.manifest["source_sha256"])
    print(candidate.warnings)
    write_candidate_archive(candidate, "candidate-review.zip")

``target`` accepts ``pytest`` (default), ``python`` or ``robot``. ``style`` accepts
``actions`` (default) or ``calls``. Both functions accept optional ``observer``
and ``path_policy`` keyword arguments. Generation requires a nonempty ``run_id``;
it never guesses a run. Invalid source/lifecycle data raises
``CandidateGenerationError``. Storage and path-policy errors propagate normally.

``python -m examples.journal_candidates`` exercises all three targets with
synthetic observations and temporary files only.

Selection and fidelity
----------------------

All candidates have ``observed_path_only=True``. A journal proves observations,
not the entire intended workflow, its future branches or its external state.

* Wire schemas, duplicate JSON keys and append order validate across the whole
  bounded byte snapshot. Lifecycle/command checks then apply to the selected run:
  mutated start/completion inputs, duplicate completions, cyclic parents and
  invalid parent spans are rejected. An uncommitted final fragment is ignored
  and explicitly reported.
* Start and completion snapshots become one invocation. Only successful completed
  roots are proposed. Failed, cancelled, skipped, dry-run and unfinished roots
  exclude their descendants. A completion-only record is marked as partial.
* Valid recorded loop/branch/parallel/retry inputs remain intact. Their observed
  children are covered by the parent source, avoiding duplicate iterations or
  attempts. Retry attempt boundaries are listed only when source matching proves
  them; unavailable boundaries stay unknown. Recorded unexecuted branch inputs
  may remain in that source; no additional branch is invented.
* With insufficient sequential control source, successful observed children form
  an explicitly labelled observed-path fallback. The manifest retains parent
  IDs and exclusions. A missing parallel source excludes that subtree: append
  order is insufficient to reconstruct a concurrent replay schedule.
* Unknown commands, redacted/unsupported inputs and invalid command signatures
  remain exclusions with reasons. Outcomes are evidence, never input parameters.
  An empty selection generates an explicitly failing candidate, not a passing
  empty test.

Source positional/keyword shapes and safe encoded parallel-branch argument text
are retained. Only validation parses the encoded branch structure. Unresolved
``${secrets.name}`` / ``secret://name`` references survive storage and generation.
Journal writes inspect encoded branches before persistence, mask known resolved
input strings/dynamic keys and record non-replayable reasons. The importer
sanitizes external input too; it never evaluates arbitrary log text or repr.

Validation and provenance
-------------------------

The manifest records the source SHA-256, selected run, actual source line numbers
and append sequences, lifecycle/parent/status evidence, emissions/exclusions,
retry attempts, code/action hashes, target/style and validation scope. Hashes
identify content; they are not digital signatures. If the source changes after
reading, the manifest still identifies the consumed byte snapshot.

Command checks cover live names, nested action structure, required arguments and
call signatures. Python/pytest artifacts pass AST parsing. Robot artifacts use
the established renderer and AST parsing of its embedded Python expressions;
this does not claim a Robot execution. The real executor's dry-run path is used
with enclosing journal capture unbound. No callable is dispatched or secret
reference resolved. Dynamic inputs and native results stay unverified.

Review content is sealed against later action/manifest mutation. Export/import
reject stale review data. A resolved-secret mask that would alter generated code
causes an explicit error instead of returning invalid code labelled as checked.

The source limit is 64 MiB, with 8 MiB per record, 100,000 records, 10,000 selected
steps and at most 64 parent levels. Candidate action validation allows 10,000
nodes and 32 structured control levels. The JSON review bundle and uncompressed
ZIP content each have a 16 MiB limit. Visible GUI views are limited to 200,000
characters each, with a truncation status; the cached review remains complete.

CLI, commands and export
------------------------

Journal mode returns the complete JSON review bundle on stdout::

    je_auto_control codegen --from-log run.jsonl --run-id selected-run
    je_auto_control codegen --from-log run.jsonl --run-id selected-run --target robot -o review.zip

``-o`` in journal mode requires a ``.zip`` destination. The atomic archive contains
``candidate.py`` or ``candidate.robot``, ``actions.json``, ``manifest.json`` and
``README.txt``. Existing archives may be replaced as one complete artifact.
``--name`` and ``--failure-bundle`` apply to legacy action-file mode. That mode
retains its calls-style default and source-code output.

``AC_generate_candidate_from_log`` and MCP ``ac_generate_candidate_from_log``
take ``path``, ``run_id``, optional ``target``, ``style`` and ``output`` (ZIP).
Script Builder exposes the same fields. MCP provides cooperative progress and
cancellation, with no partial candidate. Private journal access requires drive
permission even when no export is requested. Source/output paths honor current,
client and enclosing roots, including revocation around progress callbacks.
Cancellation before atomic export prevents replacement; no cancellation callback
runs after a committed export to relabel it as cancelled.

GUI review and import
----------------------

Use **Actions → Review journal candidate** in Recording Editor or Script Builder.
The owned background dialog shows code, changes from the current actions,
provenance and warnings. Choose a journal/run and use the dialog's **Actions →
Generate and validate**. Changing inputs clears the prior review; closing the
dialog/editor cancels work and discards late results. Four interface languages
are supported.

From Script Builder, **Import into Script Builder** explicitly replaces editor
data and retains provenance in saved JSON metadata. It never invokes Run. If the
editor changed after the diff baseline, transfer is refused; reopen review against
the new baseline. Recording Editor provides review/export, while transfer is
available from the Builder-owned dialog. Export uses the reviewed snapshot and
rechecks current roots and authority. Native-device and paid-API acceptance remain
deferred.
