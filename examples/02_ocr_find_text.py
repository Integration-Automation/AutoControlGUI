"""Locate on-screen text via OCR and click it.

Install the OCR backend that fits your install constraint::

    pip install pytesseract   # plus tesseract.exe on PATH (Windows)
    pip install easyocr       # bundled CRNN model, larger download
    pip install paddlepaddle paddleocr  # best CJK quality

If you pre-install only one of those, ``find_text_matches`` auto-picks
it via ``je_auto_control.utils.ocr.backends.get_backend``.
"""
import je_auto_control as ac


def main() -> None:
    target = "Sign in"
    matches = ac.find_text_matches(target, lang="eng", min_confidence=60.0)
    if not matches:
        print(f"OCR did not find {target!r} on screen.")
        return
    hit = matches[0]
    print(
        f"matched {hit.text!r} @ ({hit.x}, {hit.y}) "
        f"{hit.width}x{hit.height} conf={hit.confidence:.1f}",
    )

    # Click the centre of the first match. ``click_text`` does the same
    # thing as the two lines below, but this shows the data flow.
    cx, cy = hit.center
    ac.set_mouse_position(cx, cy)
    ac.click_mouse("mouse_left")


if __name__ == "__main__":
    main()
