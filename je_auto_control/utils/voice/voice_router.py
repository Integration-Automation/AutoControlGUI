"""Route recognized speech to automation actions, hands-free.

A ``VoiceRouter`` maps trigger *phrases* to ``AC_*`` action lists: feed it the
text of a recognized utterance and it runs the closest registered command. Phrase
matching reuses the project's fuzzy matcher, so "save the file" still fires a
``"save file"`` command despite recogniser noise.

Speech-to-text is intentionally **out of scope and injectable**: the router takes
already-recognised *text*. A real microphone/Vosk recogniser is supplied as a
``recognizer`` callable to :meth:`VoiceRouter.listen_once`, which keeps the
routing logic fully unit-testable without audio or any speech dependency. Imports
no ``PySide6``.
"""
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class VoiceCommand:
    """A trigger phrase and the action list it runs."""

    phrase: str
    actions: List[Any] = field(default_factory=list)


class VoiceRouter:
    """Match recognized text to a registered command and dispatch its actions."""

    def __init__(self, *, threshold: float = 0.7) -> None:
        """``threshold`` is the minimum fuzzy score (0..1) for a phrase match."""
        self._commands: List[VoiceCommand] = []
        self._threshold = threshold
        # The default router is shared by the executor and the MCP handlers:
        # match() scored one snapshot and indexed another, so a concurrent
        # register ran the wrong command, and clear() raised IndexError.
        self._lock = threading.Lock()

    def register(self, phrase: str, actions: List[Any]) -> None:
        """Register (or replace) the command for ``phrase``."""
        with self._lock:
            self._commands = [c for c in self._commands if c.phrase != phrase] + [
                VoiceCommand(phrase, list(actions))]

    def phrases(self) -> List[str]:
        """Return the registered trigger phrases."""
        with self._lock:
            return [command.phrase for command in self._commands]

    def clear(self) -> None:
        """Remove all registered commands."""
        with self._lock:
            self._commands = []

    def match(self, text: str) -> Optional[VoiceCommand]:
        """Return the command whose phrase best matches ``text`` (or ``None``)."""
        from je_auto_control.utils.fuzzy import fuzzy_best_match
        with self._lock:
            commands = list(self._commands)
        best = fuzzy_best_match(text, [command.phrase for command in commands],
                                score_cutoff=self._threshold)
        return commands[best[2]] if best else None

    def dispatch(self, text: str,
                 runner: Optional[Callable[[List[Any]], Any]] = None
                 ) -> Dict[str, Any]:
        """Match ``text`` and run the command's actions; report what fired.

        ``runner`` runs an action list (defaults to the executor); inject a fake
        to test routing without executing real automation.
        """
        command = self.match(text)
        if command is None:
            return {"matched": False, "phrase": None, "result": None}
        run = runner or _default_runner
        return {"matched": True, "phrase": command.phrase,
                "result": run(command.actions)}

    def listen_once(self, recognizer: Callable[[], str],
                    runner: Optional[Callable[[List[Any]], Any]] = None
                    ) -> Dict[str, Any]:
        """Recognise one utterance via ``recognizer()`` then dispatch it."""
        return self.dispatch(recognizer(), runner)


def _default_runner(actions: List[Any]) -> Any:
    from je_auto_control.utils.executor.action_executor import execute_action
    return execute_action(actions)


default_voice_router = VoiceRouter()
