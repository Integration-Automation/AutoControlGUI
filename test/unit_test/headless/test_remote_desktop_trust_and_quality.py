"""The remote-desktop trust store, address book and quality controller.

These four modules decide who is allowed to drive this machine unattended
(`trust_list`), whether the host answering is the host that answered last time
(`fingerprint`), what the viewer offers to reconnect to (`address_book`), and
how hard the encoder is pushed when the link degrades (`adaptive_bitrate`).
They are ordinary Python -- a JSON file, a lock and some arithmetic -- but
until the `[webrtc]` extra became part of the measured install they were
imported by nothing on any CI square, because `adaptive_bitrate` reaches
`webrtc_stats` and the whole subsystem raised ImportError at module level.

What these tests are for: every one of them describes a decision the code makes
in the operator's absence. A trust entry that silently loses its label on
re-add, a known-hosts file that throws on a truncated write, a fingerprint
comparison that is case-sensitive against an SDP that is not, a downscale that
fires on a single dropped packet -- each is invisible until someone is
connected from another building.
"""
import json

import pytest

from je_auto_control.utils.remote_desktop.address_book import AddressBook
from je_auto_control.utils.remote_desktop.adaptive_bitrate import (
    AdaptiveBitrateController,
)
from je_auto_control.utils.remote_desktop.fingerprint import (
    FingerprintMismatchError, KnownHosts, extract_dtls_fingerprint,
    fingerprint_for_display, load_or_create_host_fingerprint,
    verify_dtls_fingerprint,
)
from je_auto_control.utils.remote_desktop.trust_list import TrustList
from je_auto_control.utils.remote_desktop.webrtc_stats import StatsSnapshot


# === The host's own fingerprint =============================================

def test_host_fingerprint_is_created_once_and_then_reused(tmp_path):
    """First call mints 64 hex chars; later calls return the same string."""
    target = tmp_path / "nested" / "host_fingerprint"
    first = load_or_create_host_fingerprint(target)
    assert len(first) == 64
    assert int(first, 16) >= 0  # hex, not arbitrary text
    assert load_or_create_host_fingerprint(target) == first
    assert target.read_text(encoding="utf-8").strip() == first


def test_a_truncated_fingerprint_file_is_replaced_not_trusted(tmp_path):
    """A half-written file must not become this host's identity."""
    target = tmp_path / "host_fingerprint"
    target.write_text("deadbeef", encoding="utf-8")
    minted = load_or_create_host_fingerprint(target)
    assert len(minted) == 64
    assert minted != "deadbeef"


def test_an_unwritable_fingerprint_path_still_returns_one(tmp_path):
    """Persistence is best-effort: the session gets an identity regardless."""
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    minted = load_or_create_host_fingerprint(blocker / "sub" / "fp")
    assert len(minted) == 64


# === The viewer's known-hosts map ===========================================

def test_known_hosts_survives_a_restart(tmp_path):
    path = tmp_path / "known_hosts.json"
    first = KnownHosts(path)
    first.remember("host-a", "a" * 64)
    first.remember_dtls_fingerprint("host-a", "AB:CD")
    first.touch("host-a")

    second = KnownHosts(path)
    assert second.fingerprint_for("host-a") == "a" * 64
    assert second.dtls_fingerprint_for("host-a") == "AB:CD"
    assert second.last_seen("host-a") is not None


def test_remembering_one_fingerprint_keeps_the_other(tmp_path):
    """The app-layer and DTLS fingerprints are stored side by side."""
    hosts = KnownHosts(tmp_path / "known_hosts.json")
    hosts.remember_dtls_fingerprint("host-a", "AB:CD")
    hosts.remember("host-a", "a" * 64)
    assert hosts.dtls_fingerprint_for("host-a") == "AB:CD"
    hosts.remember_dtls_fingerprint("host-a", "EF:01")
    assert hosts.fingerprint_for("host-a") == "a" * 64
    assert hosts.dtls_fingerprint_for("host-a") == "EF:01"


def test_a_legacy_plain_string_entry_is_migrated_on_load(tmp_path):
    """Files written before the DTLS fingerprint existed still open."""
    path = tmp_path / "known_hosts.json"
    path.write_text(json.dumps({"host-a": "a" * 64}), encoding="utf-8")
    hosts = KnownHosts(path)
    assert hosts.fingerprint_for("host-a") == "a" * 64
    assert hosts.dtls_fingerprint_for("host-a") is None


@pytest.mark.parametrize("payload", ["{not json", json.dumps(["a", "b"]),
                                     json.dumps({"host-a": 7})])
def test_an_unreadable_known_hosts_file_opens_empty(tmp_path, payload):
    """A corrupt store must not stop the viewer from connecting at all."""
    path = tmp_path / "known_hosts.json"
    path.write_text(payload, encoding="utf-8")
    assert KnownHosts(path).list_entries() == {}


def test_forget_reports_whether_anything_was_removed(tmp_path):
    hosts = KnownHosts(tmp_path / "known_hosts.json")
    hosts.remember("host-a", "a" * 64)
    assert hosts.forget("host-a") is True
    assert hosts.forget("host-a") is False
    assert hosts.fingerprint_for("host-a") is None


def test_list_entries_hands_back_copies(tmp_path):
    """A caller mutating the report must not rewrite the trust store."""
    hosts = KnownHosts(tmp_path / "known_hosts.json")
    hosts.remember("host-a", "a" * 64)
    hosts.list_entries()["host-a"]["app_fp"] = "tampered"
    assert hosts.fingerprint_for("host-a") == "a" * 64


# === Showing and comparing fingerprints =====================================

def test_display_form_groups_a_full_fingerprint_into_fours():
    grouped = fingerprint_for_display("ab" * 32)
    assert grouped.count(":") == 15
    assert grouped.replace(":", "") == "ab" * 32


@pytest.mark.parametrize("value, expected", [("", ""), ("short", "short")])
def test_display_form_passes_through_what_it_cannot_group(value, expected):
    assert fingerprint_for_display(value) == expected


_SDP = (
    "v=0\r\n"
    "a=fingerprint:sha-1 11:22:33\r\n"
    "m=video 9 UDP/TLS/RTP/SAVPF 96\r\n"
    "a=fingerprint:SHA-256 ab:cd:ef:01\r\n"
)


def test_the_requested_algorithm_is_the_one_extracted():
    """An offer carries several; picking the wrong line pins the wrong cert."""
    assert extract_dtls_fingerprint(_SDP, "sha-256") == "AB:CD:EF:01"
    assert extract_dtls_fingerprint(_SDP, "sha-1") == "11:22:33"
    assert extract_dtls_fingerprint(_SDP, "sha-384") is None


def test_a_non_string_offer_yields_no_fingerprint():
    assert extract_dtls_fingerprint(None) is None


@pytest.mark.parametrize("expected", ["ab:cd:ef:01", "ABCDEF01",
                                      "AB:CD:EF:01"])
def test_verification_accepts_either_spelling_of_the_same_value(expected):
    verify_dtls_fingerprint(_SDP, expected)


def test_verification_rejects_a_different_certificate():
    with pytest.raises(FingerprintMismatchError, match="mismatch"):
        verify_dtls_fingerprint(_SDP, "00:11:22:33")


def test_verification_fails_closed_when_the_offer_pins_nothing():
    with pytest.raises(FingerprintMismatchError, match="no sha-256"):
        verify_dtls_fingerprint("v=0\r\n", "AB:CD")


# === The unattended-access trust list =======================================

def test_a_trusted_viewer_is_still_trusted_after_a_restart(tmp_path):
    path = tmp_path / "trusted_viewers.json"
    TrustList(path).add("viewer-1", label="office laptop")
    reopened = TrustList(path)
    assert reopened.is_trusted("viewer-1") is True
    assert reopened.list_entries()[0]["label"] == "office laptop"


def test_re_adding_keeps_the_original_label_and_first_seen_time(tmp_path):
    """Re-authenticating must not quietly erase what the operator typed."""
    trust = TrustList(tmp_path / "trusted_viewers.json")
    trust.add("viewer-1", label="office laptop")
    added_at = trust.list_entries()[0]["added_at"]
    trust.add("viewer-1")
    entry = trust.list_entries()[0]
    assert entry["label"] == "office laptop"
    assert entry["added_at"] == added_at
    assert len(trust.list_entries()) == 1


def test_a_new_label_replaces_the_old_one(tmp_path):
    trust = TrustList(tmp_path / "trusted_viewers.json")
    trust.add("viewer-1", label="old")
    trust.add("viewer-1", label="new")
    assert trust.list_entries()[0]["label"] == "new"


def test_touch_records_use_only_for_a_viewer_already_trusted(tmp_path):
    trust = TrustList(tmp_path / "trusted_viewers.json")
    trust.touch("stranger")
    assert trust.list_entries() == []
    trust.add("viewer-1")
    assert trust.list_entries()[0]["last_used"] is None
    trust.touch("viewer-1")
    assert trust.list_entries()[0]["last_used"] is not None


def test_touch_preserves_last_used_across_a_re_add(tmp_path):
    trust = TrustList(tmp_path / "trusted_viewers.json")
    trust.add("viewer-1")
    trust.touch("viewer-1")
    last_used = trust.list_entries()[0]["last_used"]
    trust.add("viewer-1")
    assert trust.list_entries()[0]["last_used"] == last_used


@pytest.mark.parametrize("viewer_id", ["", None, 7])
def test_an_empty_or_non_string_viewer_id_is_refused(tmp_path, viewer_id):
    """A blank id would trust every viewer that fails to send one."""
    trust = TrustList(tmp_path / "trusted_viewers.json")
    with pytest.raises(ValueError):
        trust.add(viewer_id)


@pytest.mark.parametrize("viewer_id", [None, 7, b"viewer-1"])
def test_a_non_string_id_is_never_trusted(tmp_path, viewer_id):
    assert TrustList(tmp_path / "trusted_viewers.json").is_trusted(
        viewer_id) is False


def test_remove_and_clear_report_and_persist(tmp_path):
    path = tmp_path / "trusted_viewers.json"
    trust = TrustList(path)
    trust.add("viewer-1")
    trust.add("viewer-2")
    assert trust.remove("viewer-1") is True
    assert trust.remove("viewer-1") is False
    trust.clear()
    assert TrustList(path).list_entries() == []


@pytest.mark.parametrize("payload", ["{not json", json.dumps(["a"]),
                                     json.dumps({"viewers": "not a list"}),
                                     json.dumps({"viewers": [1, {}]})])
def test_an_unreadable_trust_list_opens_empty(tmp_path, payload):
    """Fail closed: a damaged file trusts nobody rather than everybody."""
    path = tmp_path / "trusted_viewers.json"
    path.write_text(payload, encoding="utf-8")
    assert TrustList(path).list_entries() == []


# === The viewer's address book ==============================================

def test_upsert_refreshes_the_matching_entry_instead_of_appending(tmp_path):
    book = AddressBook(tmp_path / "book.json")
    book.upsert(host_id="h1", server_url="ws://a", label="desk")
    first_used = book.list_entries()[0]["last_used"]
    book.upsert(host_id="h1", server_url="ws://a", mac_address="00:11:22")
    entries = book.list_entries()
    assert len(entries) == 1
    assert entries[0]["label"] == "desk"          # blank label does not erase
    assert entries[0]["mac_address"] == "00:11:22"
    assert entries[0]["last_used"] >= first_used


def test_the_same_host_on_a_different_url_is_a_different_entry(tmp_path):
    book = AddressBook(tmp_path / "book.json")
    book.upsert(host_id="h1", server_url="ws://a")
    book.upsert(host_id="h1", server_url="ws://b")
    assert len(book.list_entries()) == 2


@pytest.mark.parametrize("host_id, server_url", [("", "ws://a"), ("h1", "")])
def test_an_incomplete_target_is_refused(tmp_path, host_id, server_url):
    book = AddressBook(tmp_path / "book.json")
    with pytest.raises(ValueError):
        book.upsert(host_id=host_id, server_url=server_url)


def test_tags_are_stripped_deduplicated_and_sorted(tmp_path):
    book = AddressBook(tmp_path / "book.json")
    book.upsert(host_id="h1", server_url="ws://a")
    book.upsert(host_id="h2", server_url="ws://b")
    book.set_tags(host_id="h1", server_url="ws://a", tags=[" lab ", "", "prod"])
    book.set_tags(host_id="h2", server_url="ws://b", tags=["prod", None])
    assert book.list_entries()[0]["tags"] == ["lab", "prod"]
    # A JSON `null` is dropped, not stringified into a tag named "None".
    assert book.all_tags() == ["lab", "prod"]


def test_setting_tags_on_an_unknown_target_changes_nothing(tmp_path):
    book = AddressBook(tmp_path / "book.json")
    book.upsert(host_id="h1", server_url="ws://a")
    book.set_tags(host_id="nope", server_url="ws://z", tags=["x"])
    assert book.all_tags() == []


def test_toggle_favorite_reports_the_new_state_and_persists(tmp_path):
    path = tmp_path / "book.json"
    book = AddressBook(path)
    book.upsert(host_id="h1", server_url="ws://a")
    assert book.toggle_favorite(host_id="h1", server_url="ws://a") is True
    assert book.toggle_favorite(host_id="h1", server_url="ws://a") is False
    assert book.toggle_favorite(host_id="nope", server_url="ws://z") is False
    assert AddressBook(path).list_entries()[0]["favorite"] is False


def test_remove_and_clear_report_and_persist_for_the_book(tmp_path):
    path = tmp_path / "book.json"
    book = AddressBook(path)
    book.upsert(host_id="h1", server_url="ws://a")
    assert book.remove(host_id="h1", server_url="ws://a") is True
    assert book.remove(host_id="h1", server_url="ws://a") is False
    book.upsert(host_id="h2", server_url="ws://b")
    book.clear()
    assert AddressBook(path).list_entries() == []


@pytest.mark.parametrize("payload", ["{not json", json.dumps(["a"]),
                                     json.dumps({"entries": [1, {}, {
                                         "host_id": 7}]})])
def test_an_unreadable_address_book_opens_empty(tmp_path, payload):
    path = tmp_path / "book.json"
    path.write_text(payload, encoding="utf-8")
    assert AddressBook(path).list_entries() == []


# === The adaptive quality controller ========================================

class _FakeTrack:
    """The one thing the controller drives: a track with a target FPS."""

    def __init__(self, fps: int = 20) -> None:
        self.fps = fps
        self.calls = []

    def set_target_fps(self, value: int) -> None:
        self.calls.append(value)
        self.fps = value


def _feed(controller, count, **fields):
    for _ in range(count):
        controller.on_stats(StatsSnapshot(**fields))


def test_a_single_bad_sample_does_not_move_the_encoder():
    """Hysteresis: one dropped packet is noise, not a degraded link."""
    track = _FakeTrack(20)
    controller = AdaptiveBitrateController(track)
    _feed(controller, 1, packet_loss_pct=9.0)
    assert track.calls == []
    assert controller.current_fps == 20


def test_two_consecutive_lossy_samples_step_the_rate_down():
    track = _FakeTrack(20)
    controller = AdaptiveBitrateController(track)
    _feed(controller, 2, packet_loss_pct=9.0)
    assert track.calls == [16]


def test_a_latency_spike_downscales_the_same_way_loss_does():
    track = _FakeTrack(20)
    controller = AdaptiveBitrateController(track)
    _feed(controller, 2, rtt_ms=400.0)
    assert track.calls == [16]


def test_a_good_sample_between_two_bad_ones_resets_the_streak():
    track = _FakeTrack(20)
    controller = AdaptiveBitrateController(track)
    _feed(controller, 1, packet_loss_pct=9.0)
    _feed(controller, 1, packet_loss_pct=3.0)   # neither down nor up
    _feed(controller, 1, packet_loss_pct=9.0)
    assert track.calls == []


def test_the_rate_never_falls_through_the_floor():
    track = _FakeTrack(7)
    controller = AdaptiveBitrateController(track, floor_fps=6)
    _feed(controller, 2, packet_loss_pct=9.0)
    assert track.fps == 6
    _feed(controller, 2, packet_loss_pct=9.0)
    assert track.calls == [6]      # already at the floor: no second call


def test_climbing_back_takes_four_clean_samples_and_stops_at_the_ceiling():
    track = _FakeTrack(12)
    controller = AdaptiveBitrateController(track, max_fps=14)
    _feed(controller, 3, packet_loss_pct=0.1)
    assert track.calls == []
    _feed(controller, 1, packet_loss_pct=0.1)
    assert track.calls == [14]     # +4 would be 16; the ceiling wins
    _feed(controller, 4, packet_loss_pct=0.1)
    assert track.calls == [14]     # at the ceiling: nothing further


def test_sustained_latency_keeps_stepping_down_however_clean_the_link():
    """Loss near zero does not license a climb while RTT stays bad."""
    track = _FakeTrack(12)
    controller = AdaptiveBitrateController(track, max_fps=20)
    _feed(controller, 8, packet_loss_pct=0.1, rtt_ms=400.0)
    assert track.calls == [8, 5]   # the RTT rule downscales every two samples


def test_exceeding_the_hard_bitrate_cap_steps_down_on_the_first_sample():
    """A configured cap is a promise to the network, not a trend to confirm."""
    track = _FakeTrack(20)
    controller = AdaptiveBitrateController(track, max_bitrate_kbps=1000)
    _feed(controller, 1, bitrate_kbps=4000.0, packet_loss_pct=0.1)
    assert track.calls == [16]


def test_the_hard_cap_resets_the_quality_streaks():
    """A cap breach mid-climb must not count towards the next upscale."""
    track = _FakeTrack(12)
    controller = AdaptiveBitrateController(track, max_fps=20,
                                           max_bitrate_kbps=1000)
    _feed(controller, 3, packet_loss_pct=0.1)
    _feed(controller, 1, bitrate_kbps=4000.0)
    assert track.calls == [8]
    _feed(controller, 3, packet_loss_pct=0.1)
    assert track.calls == [8]      # the streak restarted from zero


def test_a_bitrate_under_the_cap_leaves_the_hard_path_alone():
    track = _FakeTrack(20)
    controller = AdaptiveBitrateController(track, max_bitrate_kbps=5000)
    _feed(controller, 1, bitrate_kbps=1000.0, packet_loss_pct=9.0)
    assert track.calls == []       # quality path only, and it needs two


def test_disabling_the_controller_freezes_the_rate():
    track = _FakeTrack(20)
    controller = AdaptiveBitrateController(track)
    controller.set_enabled(False)
    _feed(controller, 6, packet_loss_pct=9.0)
    assert track.calls == []
    controller.set_enabled(True)
    _feed(controller, 2, packet_loss_pct=9.0)
    assert track.calls == [16]


def test_a_controller_with_no_track_reports_no_rate():
    controller = AdaptiveBitrateController(_FakeTrack(20))
    controller._track = None       # the teardown state the host leaves behind
    controller.on_stats(StatsSnapshot(packet_loss_pct=9.0))
    assert controller.current_fps == 0


def test_a_stats_snapshot_crosses_the_json_boundary():
    snapshot = StatsSnapshot(rtt_ms=12.5, fps=30.0, bitrate_kbps=900.0,
                             packet_loss_pct=0.2, jitter_ms=3.0)
    assert json.loads(json.dumps(snapshot.to_dict()))["rtt_ms"] == 12.5
