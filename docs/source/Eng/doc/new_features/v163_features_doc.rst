Token-Budgeted Observation Delta (What Changed)
===============================================

``observation.serialize_observation`` renders *one full frame* of the UI — feeding it to a
model every turn blows the very token budget that module was built to respect, and forces the
model to re-read the whole screen just to spot the one new dialog. ``element_diff`` gives the
stable-ID correspondence between two frames but stops at matched / added / removed *element
pairs* — it does not render a compact, indexed, budget-capped delta the model can act on.

``observation_delta`` is the missing serializer: it diffs the previous and current observation,
classifies each matched element as *changed* (role / name / enabled / value / moved) or
*stable*, and renders only the churn — ``+ [i] role "name"`` (appeared) / ``- role "name"``
(vanished) / ``~ [i] role "name" (fields)`` (changed) — added and changed first, stable dropped,
capped at ``max_lines``. The model sees *what changed* instead of the whole screen again.

Pure-stdlib over element dicts; reuses ``element_diff.match_elements`` for the overlap join and
``observation.observation_index`` for reading-order indexing. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import delta_observation, delta_index, summarize_delta

    summary = delta_observation(prev_elements, curr_elements, max_lines=40)
    # + [12] dialog "Saved"
    # ~ [4] button "Submit" (enabled)
    # - button "Spinner"

    delta = delta_index(prev_elements, curr_elements)   # {added, removed, changed, stable}
    text = summarize_delta(delta, max_lines=20)

``delta_index`` returns ``{added, removed, changed, stable}`` (``changed`` items are
``{"after", "fields"}``); ``summarize_delta`` renders a ``delta_index`` result as budget-capped
``+`` / ``~`` / ``-`` lines; ``delta_observation`` indexes both frames (reading order, viewport
clip, interactive-only) then diffs and renders in one call.

Executor command
----------------

``AC_delta_observation`` (``prev`` / ``curr`` / ``viewport`` / ``max_elements`` / ``max_lines``
/ ``interactive_only`` → ``{summary, added, removed, changed}``) is exposed as the MCP tool
``ac_delta_observation`` (read-only) and as the Script Builder command **Observation: Delta
(what changed)** under **Native UI**.
