"""registry.webrtc_usb_client() exposes the live WebRTC viewer's USB client."""
from je_auto_control.utils.remote_desktop.registry import registry


def test_webrtc_usb_client_none_when_no_viewer():
    # No WebRTC viewer is active in a fresh process.
    registry._webrtc_viewer = None  # noqa: SLF001  test setup
    assert registry.webrtc_usb_client() is None


def test_webrtc_usb_client_delegates_to_viewer():
    sentinel = object()

    class _FakeViewer:
        def usb_client(self):
            return sentinel

    registry._webrtc_viewer = _FakeViewer()  # noqa: SLF001  test setup
    try:
        assert registry.webrtc_usb_client() is sentinel
    finally:
        registry._webrtc_viewer = None  # noqa: SLF001  cleanup


def test_webrtc_usb_client_tolerates_viewer_without_method():
    class _OldViewer:
        pass

    registry._webrtc_viewer = _OldViewer()  # noqa: SLF001  test setup
    try:
        assert registry.webrtc_usb_client() is None
    finally:
        registry._webrtc_viewer = None  # noqa: SLF001  cleanup
