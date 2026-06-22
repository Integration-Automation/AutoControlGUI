Voice-Command Router
====================

``VoiceRouter`` maps spoken trigger *phrases* to ``AC_*`` action lists: feed it
the text of a recognized utterance and it runs the closest registered command —
hands-free triggering of automation flows. Phrase matching reuses the project's
fuzzy matcher, so "save the file" still fires a ``"save file"`` command despite
recogniser noise.

Speech-to-text is intentionally **out of scope and injectable**: the router takes
already-recognised *text*. A real microphone/Vosk recogniser is supplied as a
``recognizer`` callable to :meth:`VoiceRouter.listen_once`, which keeps the
routing logic fully unit-testable without audio or any speech dependency. Imports
no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import VoiceRouter

    router = VoiceRouter(threshold=0.7)
    router.register("save file", [["AC_hotkey", {"keys": ["ctrl", "s"]}]])
    router.register("close window", [["AC_close_window", {}]])

    router.dispatch("save the file")     # fuzzy-matches -> runs the save actions

    # with a real recogniser (any callable returning text):
    def vosk_listen() -> str:
        ...                              # capture audio, return transcript
    router.listen_once(vosk_listen)

``dispatch`` (and ``listen_once``) accept a ``runner`` to execute the action list
— it defaults to the executor; inject a fake to test routing without running real
automation. ``match`` returns the best ``VoiceCommand`` at or above ``threshold``
(or ``None``); ``register`` replaces an existing phrase; ``phrases`` / ``clear``
inspect and reset.

Executor commands
-----------------

A module-level default router backs the executor/MCP surfaces:

================================ ===================================================
Command                          Effect
================================ ===================================================
``AC_voice_register``            Map a ``phrase`` to an ``actions`` list.
``AC_voice_dispatch``            Run the command best matching recognized ``text``.
``AC_voice_list``                List registered phrases.
``AC_voice_clear``               Remove all registered commands.
================================ ===================================================

``actions`` accepts a list or a JSON-string list (so the visual builder works).
The same operations are exposed as MCP tools (``ac_voice_register`` /
``ac_voice_dispatch`` / ``ac_voice_list`` / ``ac_voice_clear``) and as Script
Builder commands under **Agent**.
