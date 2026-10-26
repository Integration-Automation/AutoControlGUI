"""Exclude actual host private stores and evidence roots without reserving ordinary output basenames."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.transfer_cache import private_cache_path


def _private_files(runtime: Any, actors: tuple[dict, ...]) -> tuple[Path, ...]:
    databases = (Path(runtime.store.path), private_cache_path(runtime.store.path))
    files = [path for database in databases for path in
             (database, *(database.with_name(database.name + suffix) for suffix in ('-wal', '-shm', '-journal')))]
    files.extend(Path(actor['store_path']) for actor in actors if actor.get('store_path'))
    files.extend(Path(path) for path in runtime.source_private_files)
    return tuple(path.expanduser().resolve() for path in files)


def _same_file(path: Path, private: Path) -> bool:
    if path == private:
        return True
    try:
        return path.samefile(private)
    except FileNotFoundError:
        return False


@dataclass(frozen=True)
class SourceFilePolicy:
    """Compose existing root/origin policy with current actual runtime and principal-store ownership."""

    policy: Any
    runtime: Any
    actors: tuple[dict, ...]
    historical: tuple[Any, ...] = ()

    @property
    def spec(self) -> Any:
        """Keep the original task specification; private files grant no replacement root authority."""
        return self.policy.spec

    def path(self, value: Any) -> str:
        """Deny current private locations and exact file identities before a source byte descriptor opens."""
        path = Path(self.policy.path(value))
        for ceiling in self.historical:
            ceiling.path(str(path))
        if (path.is_relative_to(Path(self.runtime.evidence.root).resolve())
                or self.runtime.evidence.cache.is_private(path)
                or any(_same_file(path, private) for private in _private_files(self.runtime, self.actors))):
            raise AgentTaskError('private runtime or principal files cannot be exported')
        return str(path)
