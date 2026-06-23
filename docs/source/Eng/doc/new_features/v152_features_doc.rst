Token-Budgeted A11y Text Observation
====================================

``screen_state.describe_screen`` returns role *counts* plus a flat list of control
labels — but no stable per-element index, no ``[12] button "Submit" @(x,y)`` lines, no
viewport clipping, and no element cap / token budget. Modern desktop and web agents
feed a *flattened, indexed, viewport-pruned* text block (the "accessibility tree as the
text observation" pattern) and then act by index ("click [12]"). This builds that
observation and the index behind it, pairing with :doc:`v138_features_doc` and
``set_of_marks``.

Pure-stdlib over plain element dicts (``role`` / ``name`` / ``x`` / ``y`` / ``width`` /
``height``, optionally nested ``children``), so it is fully unit-testable. Imports no
``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (serialize_observation, observation_index,
                                 flatten_tree)

    text = serialize_observation(a11y_tree, viewport=(0, 0, 1920, 1080),
                                 max_elements=60)
    # [0] button "Save" @(30,20)
    # [1] textbox "Search" @(140,20)
    # ... feed `text` to the model; it replies "click [1]"

    target = observation_index(a11y_tree)[1]      # the structured element behind [1]
    click(*[target["x"] + target["width"] // 2, target["y"] + target["height"] // 2])

``flatten_tree`` flattens a nested element tree, keeping only interactive roles by
default. ``observation_index`` clips to the ``viewport``, orders top-to-bottom /
left-to-right, caps at ``max_elements`` and assigns a stable ``index``.
``serialize_observation`` renders those as ``[i] role "name" @(cx,cy)`` lines.

Executor commands
-----------------

``AC_serialize_observation`` (``elements`` / ``viewport`` / ``max_elements`` →
``{observation, count}``) and ``AC_observation_index`` (same inputs →
``{count, elements}``). They are exposed as the MCP tools ``ac_serialize_observation``
/ ``ac_observation_index`` and as Script Builder commands under **Native UI**.
