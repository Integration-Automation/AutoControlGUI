"""The aiortc-shaped doubles the WebRTC tests share.

Six test modules -- host session, host channels, host inbox, viewer session,
viewer media, viewer control -- all stand the same two classes up against the
same three collaborators, and every one of those collaborators is a boundary
we deliberately do not cross in a unit test:

* **`RTCPeerConnection`** would start ICE traffic against public STUN
  servers from a CI runner.
* **`ScreenVideoTrack`** would open a screen grabber, which on a headless
  runner is either absent or a black rectangle.
* **The asyncio bridge** would queue work onto a background event loop that
  no test is running, so nothing would ever be observed.

What is faked is only the aiortc surface: the doubles record what they were
handed and hand back what the real objects hand back. The code under test --
which transceiver the host adds, which slot the viewer replaces, which
envelope goes out on which channel -- is never replaced.

`FakePeerConnection` carries both ends' surface in one class on purpose. It
stands in for one aiortc type, and splitting it per direction would mean two
doubles drifting apart from the same original.

Nothing here is a test; the file is named so pytest does not collect it.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import Future


class Channel:
    """A DataChannel: records its handlers, and what was sent on it."""

    def __init__(self, label: str = "ctrl",
                 ready_state: str = "connecting") -> None:
        self.label = label
        self.readyState = ready_state   # noqa: N815  # reason: the aiortc name
        self.handlers = {}
        self.sent = []
        self.send_error = None

    def on(self, event):
        def _register(func):
            self.handlers[event] = func
            return func
        return _register

    def fire(self, event, *args):
        return self.handlers[event](*args)

    def send(self, payload):
        if self.send_error is not None:
            raise self.send_error
        self.sent.append(payload)


class Track:
    """A MediaStreamTrack: a kind, and whether anybody stopped it."""

    def __init__(self, kind: str = "video", **kwargs) -> None:
        self.kind = kind
        self.kwargs = kwargs
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class FrameTrack:
    """Yields a scripted sequence of frames, then raises to end the stream."""

    def __init__(self, *frames, ending=None) -> None:
        from aiortc.mediastreams import MediaStreamError
        self.frames = list(frames)
        self._ending = ending if ending is not None else MediaStreamError()

    async def recv(self):
        if not self.frames:
            raise self._ending
        return self.frames.pop(0)


class Sender:
    def __init__(self, track=None) -> None:
        self.track = track
        self.replaced = []
        self.replace_error = None

    def replaceTrack(self, track):      # noqa: N802  # reason: the aiortc name
        if self.replace_error is not None:
            raise self.replace_error
        self.replaced.append(track)
        self.track = track


class Transceiver:
    def __init__(self, kind: str, track=None,
                 direction: str = "recvonly") -> None:
        self.kind = kind
        self.sender = Sender(track)
        self.direction = direction


class FakePeerConnection:
    """The aiortc surface both ends touch, and nothing beyond it."""

    instances: list = []

    def __init__(self, configuration=None) -> None:
        self.configuration = configuration
        self.connectionState = "new"    # noqa: N815  # reason: the aiortc name
        self.iceGatheringState = "new"  # noqa: N815  # reason: the aiortc name
        self.tracks = []
        self.transceivers = []
        self.channels = []
        self.handlers = {}
        self.local_sdp = "v=0 local-sdp"
        self.remote_descriptions = []
        self.closed = False
        self.stats = {}
        self.stats_error = None
        self.answer_error = None
        self.remote_description_error = None
        FakePeerConnection.instances.append(self)

    # --- the aiortc surface --------------------------------------------------

    def addTrack(self, track):          # noqa: N802  # reason: the aiortc name
        self.tracks.append(track)

    def addTransceiver(self, kind, direction):   # noqa: N802  # the aiortc name
        self.transceivers.append((kind, direction))

    def getTransceivers(self):          # noqa: N802  # reason: the aiortc name
        return list(self.transceivers)

    def createDataChannel(self, label):  # noqa: N802  # reason: the aiortc name
        channel = Channel(label)
        self.channels.append(channel)
        return channel

    def on(self, event):
        def _register(func):
            self.handlers[event] = func
            return func
        return _register

    async def createOffer(self):        # noqa: N802  # reason: the aiortc name
        return "offer-object"

    async def createAnswer(self):       # noqa: N802  # reason: the aiortc name
        if self.answer_error is not None:
            raise self.answer_error
        return "answer-object"

    async def setLocalDescription(self, description):   # noqa: N802
        self.local_description_arg = description

    async def setRemoteDescription(self, description):  # noqa: N802
        if self.remote_description_error is not None:
            raise self.remote_description_error
        self.remote_descriptions.append(description)

    async def getStats(self):           # noqa: N802  # reason: the aiortc name
        if self.stats_error is not None:
            raise self.stats_error
        return self.stats

    async def close(self):
        self.closed = True

    @property
    def localDescription(self):         # noqa: N802  # reason: the aiortc name
        return type("_Desc", (), {"sdp": self.local_sdp})()

    # --- test helpers --------------------------------------------------------

    def channel(self, label: str) -> Channel:
        return next(c for c in self.channels if c.label == label)

    def fire(self, event, *args):
        return self.handlers[event](*args)

    def video_slots(self, count: int = 2):
        """Offer `count` video transceivers, as a host's offer would."""
        self.transceivers = [Transceiver("video") for _ in range(count)]
        return self.transceivers

    def complete_ice_gathering(self) -> None:
        """Finish gathering and notify whoever subscribed to the change."""
        self.iceGatheringState = "complete"
        self.handlers["icegatheringstatechange"]()


class Bridge:
    """The asyncio bridge, minus the loop: run the work here and now.

    `submit` mirrors `run_coroutine_threadsafe` in parking any exception on
    the future rather than raising into the caller, because that is where
    `create_offer`'s and `stop`'s error handling reads it from.
    """

    def __init__(self) -> None:
        self.deferred = []

    def submit(self, coro) -> Future:
        future: Future = Future()
        try:
            future.set_result(asyncio.run(coro))
        except BaseException as error:   # noqa: BLE001  # reason: mirrors run_coroutine_threadsafe, which parks any exception on the future rather than raising into the submitting thread
            future.set_exception(error)
        return future

    def call_soon(self, callback, *args) -> None:
        self.deferred.append((callback, args))
        callback(*args)


class HangingBridge:
    """A bridge whose work never lands: every future times out."""

    def submit(self, coro) -> Future:
        coro.close()
        future: Future = Future()
        future.set_exception(asyncio.TimeoutError())
        return future

    def call_soon(self, callback, *args) -> None:
        return None


class AuditLog:
    """The audit log, without the write to the user's real home directory."""

    def __init__(self) -> None:
        self.events = []
        self.error = None

    def log(self, event_type, **fields) -> None:
        if self.error is not None:
            raise self.error
        self.events.append((event_type, fields))

    @property
    def event_types(self) -> list:
        return [event for event, _ in self.events]


class MicReceiver:
    """Host side of the raw-PCM mic uplink: what arrived, and was it closed."""

    def __init__(self) -> None:
        self.chunks = []
        self.started = False
        self.stopped = False
        self.stop_error = None

    def start(self) -> None:
        self.started = True

    def on_chunk(self, chunk) -> None:
        self.chunks.append(chunk)

    def stop(self) -> None:
        if self.stop_error is not None:
            raise self.stop_error
        self.stopped = True


class MicSender:
    """Viewer side of the same uplink; it is handed the channel to write to."""

    def __init__(self, channel) -> None:
        self.channel = channel
        self.started = False
        self.running = True
        self.stop_error = None

    def start(self) -> None:
        self.started = True

    def is_running(self) -> bool:
        return self.running

    def stop(self) -> None:
        if self.stop_error is not None:
            raise self.stop_error
        self.running = False


class Stoppable:
    """Something the teardown path is expected to stop, and may fail to."""

    def __init__(self, error=None) -> None:
        self.stopped = False
        self._error = error

    def stop(self) -> None:
        if self._error is not None:
            raise self._error
        self.stopped = True


async def noop_ice_gathering(pc, timeout=None):
    """Stand in for `wait_for_ice_gathering`: there are no candidates here."""
    return None
