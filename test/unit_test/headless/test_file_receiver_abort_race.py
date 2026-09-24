"""A transfer aborted before or while FILE_BEGIN opens its part file (no network).

``handle_begin`` opened the ``.part`` file before registering the transfer, so
an abort from the viewer disconnecting in between found nothing to cancel;
the part file and its open handle stayed. The macOS CI run of
``test_a_viewer_disconnecting_mid_upload_leaves_no_part_file`` hit it.
"""
from je_auto_control.utils.remote_desktop import file_transfer
from je_auto_control.utils.remote_desktop.file_transfer import (
    FileReceiver, encode_begin, new_transfer_id,
)


def test_an_abort_before_the_begin_cancels_it(tmp_path):
    completed = []
    receiver = FileReceiver(on_complete=lambda *args: completed.append(args))
    transfer_id = new_transfer_id()
    receiver.abort(transfer_id, "viewer disconnected")
    receiver.handle_begin(encode_begin(transfer_id, str(tmp_path / "big.bin"), 10))
    assert list(tmp_path.iterdir()) == []
    assert completed and completed[0][1] is False


def test_an_abort_while_the_part_file_opens_removes_it(tmp_path, monkeypatch):
    receiver = FileReceiver()
    transfer_id = new_transfer_id()
    real_open = open

    def open_then_disconnect(*args, **kwargs):
        handle = real_open(*args, **kwargs)
        receiver.abort(transfer_id, "viewer disconnected")   # the other thread's stop()
        return handle

    monkeypatch.setattr(file_transfer, "open", open_then_disconnect, raising=False)
    receiver.handle_begin(encode_begin(transfer_id, str(tmp_path / "big.bin"), 10))
    assert list(tmp_path.iterdir()) == []


def test_a_normal_transfer_is_unaffected(tmp_path):
    from je_auto_control.utils.remote_desktop.file_transfer import encode_chunk, encode_end
    receiver = FileReceiver()
    transfer_id = new_transfer_id()
    receiver.handle_begin(encode_begin(transfer_id, str(tmp_path / "ok.bin"), 3))
    receiver.handle_chunk(encode_chunk(transfer_id, b"abc"))
    receiver.handle_end(encode_end(transfer_id, "ok", None))
    assert (tmp_path / "ok.bin").read_bytes() == b"abc"
