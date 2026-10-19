"""Coordinate two real local workspaces over temporary loopback HTTP without applying preferences or running scripts."""
from pathlib import Path
from tempfile import TemporaryDirectory

from examples.causal_peer_control import loopback_server
from je_auto_control import CausalConfigStore, SyncControlRequest, SyncOutbox, SyncWorkspace
from je_auto_control.utils.path_guard import PathPolicy


def configuration(directory: Path, endpoint: str, origin: str, theme: str) -> dict[str, object]:
    """Select native workspace INI and an explicit script source; every state file belongs to the temporary root."""
    root = directory / origin
    root.mkdir()
    (root / 'workspace.ini').write_text('[workspace]\ntheme=' + theme + '\n', encoding='utf-8')
    scripts = root / 'scripts'
    scripts.mkdir()
    (scripts / 'login.json').write_text('[["AC_log", {"message": "never executed"}]]', encoding='utf-8')
    outbox = root / 'outbox.sqlite3'
    SyncOutbox(outbox).identity(endpoint, 'example', origin=origin)
    return {'schema_version': 1, 'endpoint': endpoint, 'user_id': 'example', 'outbox_path': str(outbox),
            'profiles': [
                {'kind': 'workspace', 'state_path': str(root / 'adapters.sqlite3'),
                 'source': {'path': str(root / 'workspace.ini')}},
                {'kind': 'scripts', 'state_path': str(root / 'adapters.sqlite3'),
                 'source': {'path': str(scripts), 'paths': ['login.json'] if origin == 'desktop' else []}}]}


def workflow(directory: Path, endpoint: str) -> None:
    """Review offline concurrency, publish inert data and discard an obsolete generation explicitly."""
    policy = PathPolicy([directory])
    left_config = configuration(directory, endpoint, 'desktop', 'light')
    right_config = configuration(directory, endpoint, 'laptop', 'dark')
    left, right = (SyncWorkspace(config, path_policy=policy) for config in (left_config, right_config))
    left.capture()
    right.capture()
    left.synchronize()
    conflicts = right.synchronize().conflicts
    left.synchronize()
    heads = left.review('workspace')
    left.resolve('workspace', 'theme', {'value': 'light'}, observed=heads)
    left.synchronize()
    right.synchronize()
    generation = right.materialize(directory / 'cache')
    restarted = SyncWorkspace(left_config, path_policy=policy)
    (directory / 'desktop/workspace.ini').write_text('[workspace]\ntheme=dark\n', encoding='utf-8')
    restarted.capture()
    restarted.control(SyncControlRequest('retire', peer_id='desktop'))
    request = SyncControlRequest('full_resync', operation_id='recover', discard_pending=True)
    reset = restarted.control(request)
    after_reset = SyncWorkspace(left_config, path_policy=policy).synchronize()
    print(f'conflicts={conflicts}; profile_files={generation.file_count}; reset_revision={reset.revision}; '
          f'replayed_after_reset={after_reset.captured}; pending={after_reset.pending}; external_calls=0')


def main() -> None:
    """Run a loopback-only example using disposable sources, server/outbox databases and an inert profile cache."""
    with TemporaryDirectory(prefix='autocontrol-workspace-http-') as temporary:
        directory = Path(temporary)
        with loopback_server(CausalConfigStore(directory / 'server.sqlite3')) as endpoint:
            workflow(directory, endpoint)


if __name__ == '__main__':
    main()
