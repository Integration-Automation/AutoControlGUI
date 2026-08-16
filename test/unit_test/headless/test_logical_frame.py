"""Headless tests for capturing in mouse-coordinate space. No Qt, no screen."""
from je_auto_control.utils.monitor_layout import (
    grab_logical, logical_scale, logical_virtual_rect, needs_rescale,
)


class FakeImage:
    """Minimal PIL-Image stand-in recording the resize / crop it was asked for."""

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.resized_to = None
        self.cropped_to = None

    @property
    def size(self):
        return self.width, self.height

    def resize(self, size, _resample=None):
        out = FakeImage(*size)
        out.resized_to = size
        return out

    def crop(self, box):
        out = FakeImage(box[2] - box[0], box[3] - box[1])
        out.cropped_to = box
        return out


class FakeGrab:
    """``ImageGrab`` stand-in: separate sizes for the primary and full desktop."""

    def __init__(self, primary=(1920, 1080), full=(3840, 1244)):
        self._primary = primary
        self._full = full
        self.calls = []

    def grab(self, *, all_screens=False, **_kwargs):
        self.calls.append(all_screens)
        return FakeImage(*(self._full if all_screens else self._primary))


def _metrics(x=0, y=-164, width=3456, height=1244):
    """A mixed-DPI desktop: logical 3456 wide against a 3840 physical capture."""
    return lambda index: {76: x, 77: y, 78: width, 79: height}[index]


def test_logical_scale_and_needs_rescale_are_pure():
    assert logical_scale((3840, 1244), (3456, 1244)) == (3840 / 3456, 1.0)
    assert needs_rescale((3840, 1244), (3456, 1244))
    assert not needs_rescale((3456, 1244), (3456, 1244))
    # nothing to compare against -> do not rescale on a guess
    assert not needs_rescale((100, 100), (0, 0))


def test_logical_virtual_rect_reports_a_negative_origin():
    # a monitor above the primary one puts the desktop origin at a negative y
    assert logical_virtual_rect(_metrics()) == (0, -164, 3456, 1244)


def test_logical_virtual_rect_is_none_when_unreported():
    assert logical_virtual_rect(_metrics(width=0, height=0)) is None


def test_grab_logical_rescales_a_physical_capture_to_mouse_space():
    # unscaled, a point read off the 3840-wide capture lands ~116 px away from
    # where it was clicked on this desktop
    grabber = FakeGrab()
    image, origin_x, origin_y = grab_logical(grabber=grabber, metrics=_metrics())
    assert image.size == (3456, 1244)
    assert (origin_x, origin_y) == (0, -164)
    assert grabber.calls == [True]


def test_grab_logical_leaves_a_matching_capture_alone():
    grabber = FakeGrab(full=(3456, 1244))
    image, _x, _y = grab_logical(grabber=grabber, metrics=_metrics())
    assert image.resized_to is None


def test_grab_logical_primary_only_skips_the_virtual_desktop():
    grabber = FakeGrab()
    image, origin_x, origin_y = grab_logical(
        all_screens=False, grabber=grabber, metrics=_metrics())
    assert image.size == (1920, 1080)
    assert (origin_x, origin_y) == (0, 0)
    assert grabber.calls == [False]


def test_grab_logical_crops_after_rescaling_not_before():
    # cropping through ImageGrab's bbox happens in physical pixels and would cut
    # the wrong place on a scaled screen, so the crop must be on the rescaled frame
    grabber = FakeGrab()
    image, origin_x, origin_y = grab_logical(
        (100, 0, 600, 400), grabber=grabber, metrics=_metrics())
    assert image.cropped_to == (100, 164, 700, 564)
    assert image.size == (600, 400)
    assert (origin_x, origin_y) == (100, 0)


def test_grab_logical_region_origin_is_the_region_corner():
    grabber = FakeGrab()
    _image, origin_x, origin_y = grab_logical(
        (10, -50, 100, 100), grabber=grabber, metrics=_metrics())
    assert (origin_x, origin_y) == (10, -50)
