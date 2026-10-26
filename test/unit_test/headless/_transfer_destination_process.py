"""An owned background destination process supplies an independent registry, account and runtime for HTTP tests."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from threading import Event

from je_auto_control.utils.admin import admin_client
from je_auto_control.utils.agent_runtime.service import AgentRuntimeService
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from je_auto_control.utils.rbac.users import UserStore
from je_auto_control.utils.rest_api.rest_server import RestApiServer


def main() -> None:
    """Keep all effects in the explicitly supplied fixture directory and stop on its private control marker."""
    config = json.load(sys.stdin)
    directory = Path(config['directory']).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    users = UserStore(directory / 'users.json')
    users.add_user(user_id='recipient', display_name='Destination recipient', role='admin')
    token = users.rotate_token('recipient')
    actor = AuthorizationContext('recipient', 'admin', store_path=str(users.path))
    outputs = directory / 'outputs'
    outputs.mkdir()
    book = admin_client.AdminConsoleClient(persist_path=directory / 'source-hosts.json')
    book.add_host('source', config['source_url'], config['source_token'])
    admin_client._default_console = book
    service = AgentRuntimeService(directory / 'service', targets={})
    with authorization_scope(actor):
        service.runtime.target_profiles.control('register', {'name': 'import-files', 'kind': 'files',
            'allowed_tools': ['AC_workflow_manifest'], 'roots': [str(outputs)], 'apps': [], 'settings': {}})
    server = RestApiServer(port=0, token='owned-destination-service', user_store=users,
                          agent_runtime=service.runtime, enable_audit=False, use_environment_users=False)
    try:
        service.start()
        server.start()
        ready = directory / 'ready.json'
        temporary = directory / 'ready.tmp'
        temporary.write_text(json.dumps({'pid': os.getpid(), 'parent_pid': os.getppid(),
                                         'url': server.base_url, 'token': token,
                                         'outputs': str(outputs)}), encoding='utf-8')
        temporary.chmod(0o600)
        temporary.replace(ready)
        while not (directory / 'stop').exists():
            Event().wait(0.05)
    finally:
        server.stop()
        service.close()


if __name__ == '__main__':
    main()
