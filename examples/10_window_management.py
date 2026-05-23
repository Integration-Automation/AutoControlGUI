"""Find, focus, and wait for a window by title.

Cross-platform note: ``list_windows`` / ``focus_window`` etc. are
fully implemented on Windows and have stubs on macOS / Linux that
raise a clear error — adjust the title substring below to a window
you actually have open before running.
"""
import je_auto_control as ac


def main() -> None:
    print("currently visible top-level windows:")
    for hwnd, title in ac.list_windows():
        if title.strip():
            # Some real-world titles contain glyphs your console encoding
            # can't render — use ``ascii(...)`` so the demo never crashes
            # on a stray unicode char.
            print(f"  {hwnd!s:>40}  {ascii(title)}")

    target = "Notepad"
    print(f"\nsearching for a window containing {target!r}…")
    hit = ac.find_window(target)
    if hit is None:
        print(f"no match — open {target} and try again.")
        return

    hwnd, title = hit
    print(f"focusing hwnd={hwnd!s} title={ascii(title)}")
    ac.focus_window(target)

    # If the window isn't open yet, ``wait_for_window`` polls every
    # ``poll`` seconds until ``timeout`` elapses.
    later = ac.wait_for_window(target, timeout=2.0, poll=0.25)
    print(f"wait_for_window returned hwnd={later!s}")


if __name__ == "__main__":
    main()
