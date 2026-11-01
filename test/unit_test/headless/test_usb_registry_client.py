"""registry.webrtc_usb_client() exposes the live WebRTC viewer's USB client."""
from je_auto_control.utils.remote_desktop.registry import registry


def test_webrtc_usb_client_none_when_no_viewer(monkeypatch):
    # No WebRTC viewer is active in a fresh process.
    monkeypatch.setattr(registry, "_webrtc_viewer", None)
    assert registry.webrtc_usb_client() is None


def test_webrtc_usb_client_delegates_to_viewer(monkeypatch):
    sentinel = object()

    class _FakeViewer:
        def usb_client(self):
            return sentinel

    monkeypatch.setattr(registry, "_webrtc_viewer", _FakeViewer())
    assert registry.webrtc_usb_client() is sentinel


def test_webrtc_usb_client_tolerates_viewer_without_method(monkeypatch):
    class _OldViewer:
        pass

    monkeypatch.setattr(registry, "_webrtc_viewer", _OldViewer())
    assert registry.webrtc_usb_client() is None
