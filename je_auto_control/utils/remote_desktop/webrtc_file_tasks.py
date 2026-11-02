"""Run remote inbox pushes outside the event loop while preserving connection ownership and cooperative cancellation."""
from __future__ import annotations

import asyncio
import json
from concurrent.futures import CancelledError
from dataclasses import dataclass, field
from functools import partial
from threading import Event
from typing import Any, Callable, Iterable, MutableSet, Optional, Protocol

from je_auto_control.utils.exception.control_signals import raise_caused_run_interruption
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop.webrtc_file_write import _Channel

FILE_REQUEST_TASK = 'webrtc-file-request'


# pylint: disable-next=too-few-public-methods  # reason: the callback protocol represents one bound push operation
class _Push(Protocol):
    def __call__(self, local_path: str, remote_name: Optional[str] = None, *,
                 cancelled: Optional[Callable[[], bool]] = None) -> None:
        """Push a file with the originating connection's cancellation predicate."""


@dataclass
class _RequestQueue:
    channel: object
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0


_queues: dict[tuple[asyncio.AbstractEventLoop, int], _RequestQueue] = {}
_MAX_REQUESTS = 32


def start_file_request(tasks: MutableSet[asyncio.Task[Any]], sender: _Push, path: str, name: str,
                       channel: object, active: Callable[[], bool], failed: Callable[[str], None]) -> None:
    """Reserve bounded queue space before creating a tracked task; send one requested file at a time."""
    loop = asyncio.get_running_loop()
    key = (loop, id(channel))
    queue = _queues.setdefault(key, _RequestQueue(channel))
    if queue.users >= _MAX_REQUESTS:
        failed('file request queue is full; retry after current downloads finish')
        return
    queue.users += 1
    coroutine = _queued_push(queue, sender, path, name, active, failed)
    try:
        task = loop.create_task(coroutine, name=FILE_REQUEST_TASK)
    except BaseException:
        coroutine.close()
        queue.users -= 1
        if not queue.users:
            _queues.pop(key, None)
        raise
    tasks.add(task)
    task.add_done_callback(partial(_request_finished, key, queue, tasks))


async def _queued_push(queue: _RequestQueue, sender: _Push, path: str, name: str,
                       active: Callable[[], bool], failed: Callable[[str], None]) -> None:
    async with queue.lock:
        await push_requested_file(sender, path, name, active, failed)


def _request_finished(key: tuple[asyncio.AbstractEventLoop, int], queue: _RequestQueue,
                      tasks: MutableSet[asyncio.Task[Any]], task: asyncio.Task[Any]) -> None:
    tasks.discard(task)
    queue.users -= 1
    if not queue.users and _queues.get(key) is queue:
        _queues.pop(key)


async def push_requested_file(sender: _Push, path: str, name: str, active: Callable[[], bool],
                              failed: Callable[[str], None]) -> None:
    """Yield the bridge loop while a worker waits for backpressure; suppress stale failure replies."""
    stop = Event()

    def cancelled() -> bool:
        return stop.is_set() or not active()

    try:
        if cancelled():
            return
        await asyncio.to_thread(sender, path, remote_name=name, cancelled=cancelled)
    except CancelledError:
        return  # This owned background request has no separate caller waiting for its cancellation.
    except (OSError, RuntimeError, ValueError) as error:
        raise_caused_run_interruption(error)
        if not cancelled():
            failed(str(error))
    finally:
        stop.set()


def file_request_failure(channel: Optional[_Channel], name: str,
                         active: Callable[[], bool]) -> Callable[[str], None]:
    """Bind error replies to the original control channel; invoke only on that channel's event loop."""
    def reply(error: str) -> None:
        if channel is None or not active():
            return
        try:
            channel.send(json.dumps({'type': 'request_file_response', 'name': name, 'ok': False, 'error': error}))
        # pylint: disable-next=broad-exception-caught  # reason: a failed reply must not kill other bridge jobs
        except Exception as failure:  # reason: contain callback failures while preserving wrapped control signals
            raise_caused_run_interruption(failure)
            autocontrol_logger.warning('file request failure reply could not be sent: %r', failure)
    return reply


async def cancel_file_requests(tasks: Iterable[asyncio.Task[Any]]) -> None:
    """Cancel and await only named file-request tasks, leaving unrelated media tasks to their owners."""
    owned = [task for task in tuple(tasks) if task.get_name() == FILE_REQUEST_TASK]
    for task in owned:
        task.cancel()
    if owned:
        await asyncio.gather(*owned, return_exceptions=True)
