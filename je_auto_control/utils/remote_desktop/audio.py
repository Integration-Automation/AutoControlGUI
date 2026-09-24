"""Audio capture + playback wrappers around the optional ``sounddevice`` lib.

Both classes import ``sounddevice`` lazily so the package stays importable
on systems without PortAudio. ``AudioCapture`` pulls signed-int16 PCM in
fixed-size blocks via the library's callback API and forwards each block
as raw bytes; ``AudioPlayer`` accepts the same byte format and writes it
to the default (or user-chosen) output device.

Defaults are 16 kHz, mono, 50 ms blocks (1600 bytes per block, ~32 KB/s)
— small enough that audio chunks ride alongside JPEG frames over a LAN
without noticeably starving the video pipe.
"""
import threading
from dataclasses import dataclass
from typing import Any, Callable, Optional

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

DEFAULT_SAMPLE_RATE = 16_000
DEFAULT_CHANNELS = 1
DEFAULT_BLOCK_FRAMES = 800  # 50 ms at 16 kHz
SAMPLE_DTYPE = "int16"
BYTES_PER_SAMPLE = 2

AudioBlockCallback = Callable[[bytes], None]


class AudioBackendError(AutoControlException, RuntimeError):
    """Raised when ``sounddevice`` cannot be loaded or an audio device fails."""


def _load_sounddevice():
    """Import ``sounddevice`` lazily; raise a helpful error if missing.

    ``OSError`` too: sounddevice raises it when the PortAudio library
    itself cannot be found.
    """
    try:
        import sounddevice  # noqa: PLC0415  intentional lazy import
    except (ImportError, OSError) as error:
        raise AudioBackendError(
            "audio support requires 'sounddevice'. Install with: "
            "pip install sounddevice"
        ) from error
    return sounddevice


def _device_errors(sd: Any) -> tuple:
    """What a PortAudio call may raise: ``PortAudioError`` derives from ``Exception`` directly."""
    return (OSError, RuntimeError, sd.PortAudioError)


def _open_started(sd: Any, factory: Callable[[], Any]) -> Any:
    """Create a stream and start it; a stream that fails to start is closed.

    Raises :class:`AudioBackendError`: a raw ``PortAudioError`` escaped the
    ``RuntimeError`` / ``OSError`` guards around every caller, and a stream
    kept after a failed ``start()`` made every later ``start()`` a no-op.
    """
    errors = _device_errors(sd)
    try:
        stream = factory()
    except errors as error:
        raise AudioBackendError(f"audio device unavailable: {error}") from error
    try:
        stream.start()
    except errors as error:
        _close_quietly(stream, errors)
        raise AudioBackendError(f"audio device failed to start: {error}") from error
    return stream


def _close_quietly(stream: Any, errors: tuple) -> None:
    try:
        stream.close()
    except errors as error:
        autocontrol_logger.debug("audio stream close: %r", error)


def _stop_and_close(stream: Any) -> None:
    """Stop and close ``stream``; device errors on the way out are logged, never raised."""
    errors = _device_errors(_load_sounddevice())
    try:
        stream.stop()
    except errors as error:
        autocontrol_logger.debug("audio stream stop: %r", error)
    finally:
        _close_quietly(stream, errors)


def is_audio_backend_available() -> bool:
    """Return True if ``sounddevice`` can be imported."""
    try:
        _load_sounddevice()
    except AudioBackendError:
        return False
    return True


@dataclass(frozen=True)
class AudioCaptureConfig:
    """Bundled tuning knobs for :class:`RemoteDesktopHost` audio capture."""

    enabled: bool = False
    device: Optional[int] = None
    sample_rate: int = DEFAULT_SAMPLE_RATE
    channels: int = DEFAULT_CHANNELS
    block_frames: int = DEFAULT_BLOCK_FRAMES


class AudioCapture:
    """Capture mono int16 PCM blocks and hand them to ``on_block`` as bytes.

    ``on_block`` is invoked from the audio library's internal thread, so
    callers must keep it cheap (queueing / signalling is fine; CPU-heavy
    work blocks the audio pipeline).
    """

    def __init__(self, on_block: AudioBlockCallback,
                 device: Optional[int] = None,
                 sample_rate: int = DEFAULT_SAMPLE_RATE,
                 channels: int = DEFAULT_CHANNELS,
                 block_frames: int = DEFAULT_BLOCK_FRAMES) -> None:
        if not callable(on_block):
            raise TypeError("on_block must be callable")
        if sample_rate <= 0 or channels <= 0 or block_frames <= 0:
            raise ValueError(
                "sample_rate, channels and block_frames must be positive"
            )
        self._on_block = on_block
        self._device = device
        self._sample_rate = int(sample_rate)
        self._channels = int(channels)
        self._block_frames = int(block_frames)
        self._stream: Optional[Any] = None
        self._lock = threading.Lock()

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def channels(self) -> int:
        return self._channels

    @property
    def is_running(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        """Open the input stream; subsequent blocks fire ``on_block`` callbacks."""
        with self._lock:
            if self._stream is not None:
                return
            sd = _load_sounddevice()
            self._stream = _open_started(sd, lambda: sd.RawInputStream(
                samplerate=self._sample_rate,
                channels=self._channels,
                dtype=SAMPLE_DTYPE,
                blocksize=self._block_frames,
                device=self._device,
                callback=self._raw_callback,
            ))

    def stop(self) -> None:
        """Stop and release the input stream."""
        with self._lock:
            stream = self._stream
            self._stream = None
        if stream is None:
            return
        _stop_and_close(stream)

    def _raw_callback(self, indata, frames, time_info, status) -> None:
        del frames, time_info  # unused — block size is fixed
        if status:
            # An overflow flag still comes with valid samples; dropping the
            # block added a second gap on top of the glitch.
            autocontrol_logger.debug("audio capture status: %s", status)
        try:
            self._on_block(bytes(indata))
        except Exception:  # noqa: BLE001  callback isolation  # nosec B110  # reason: PortAudio callback must never raise
            # We must not propagate user callback errors back into PortAudio.
            return


class AudioPlayer:
    """Play int16 PCM bytes through the default (or chosen) output device."""

    def __init__(self, device: Optional[int] = None,
                 sample_rate: int = DEFAULT_SAMPLE_RATE,
                 channels: int = DEFAULT_CHANNELS) -> None:
        if sample_rate <= 0 or channels <= 0:
            raise ValueError("sample_rate and channels must be positive")
        self._device = device
        self._sample_rate = int(sample_rate)
        self._channels = int(channels)
        self._stream: Optional[Any] = None
        self._write_errors: tuple = (OSError, RuntimeError)
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        """Open the output stream so :meth:`play` becomes valid."""
        with self._lock:
            if self._stream is not None:
                return
            sd = _load_sounddevice()
            self._write_errors = _device_errors(sd)
            self._stream = _open_started(sd, lambda: sd.RawOutputStream(
                samplerate=self._sample_rate,
                channels=self._channels,
                dtype=SAMPLE_DTYPE,
                device=self._device,
            ))

    def play(self, chunk: bytes) -> None:
        """Write a chunk of int16 PCM bytes to the stream."""
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise TypeError("chunk must be bytes-like")
        if not chunk:
            return
        stream = self._stream
        if stream is None:
            raise RuntimeError("AudioPlayer is not running; call start() first")
        try:
            stream.write(bytes(chunk))
        except self._write_errors as error:
            # Late writes after stop / device removal — ignored so the
            # network thread keeps flowing; PortAudioError included.
            autocontrol_logger.debug("audio write dropped: %r", error)

    def stop(self) -> None:
        with self._lock:
            stream = self._stream
            self._stream = None
        if stream is None:
            return
        _stop_and_close(stream)
