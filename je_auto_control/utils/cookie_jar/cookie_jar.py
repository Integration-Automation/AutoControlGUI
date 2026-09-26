"""A small RFC 6265 cookie jar for carrying a session across HTTP calls.

``http_request`` is stateless — no session cookies persist across calls, so a
login-then-call REST flow could not carry a session headlessly. This parses
``Set-Cookie`` response headers into a jar and builds the ``Cookie`` request
header; the jar is JSON-serialisable so a session can be saved and reloaded.

Pure standard library (``json``); imports no ``PySide6``. The jar is a simple
in-memory name-value store (cookies cleared on ``max-age<=0`` or a past
``Expires``; an empty value is a cookie like any other, as RFC 6265 5.2 has
it), so behaviour is fully deterministic in CI.

It ignores ``Domain``, ``Path`` and ``Secure``: every stored cookie goes into
every ``Cookie`` header the jar builds. Keep one jar per origin, or a cookie
one host set is sent to every other host the flow calls.
"""
import datetime
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

SetCookie = Union[str, List[str]]
_Pairs = List[Tuple[str, str]]

_WSP = " \t"
# RFC 6265bis 5.6 step 1: a set-cookie-string with a CTL other than HTAB is
# ignored entirely -- "a=b\r\nX-Injected: 1" reached the Cookie header.
_CTL = re.compile(r"[\x00-\x08\x0a-\x1f\x7f]")
_MAX_AGE = re.compile(r"-?[0-9]+")                        # 5.2.2: ASCII DIGIT and "-" only
# RFC 6265 5.1.1 cookie-date grammar.
_DATE_DELIMITER = re.compile(r"[\x09\x20-\x2f\x3b-\x40\x5b-\x60\x7b-\x7e]+")
_DATE_TIME = re.compile(r"([0-9]{1,2}):([0-9]{1,2}):([0-9]{1,2})(?:[^0-9].*)?", re.S)
_DATE_DAY = re.compile(r"([0-9]{1,2})(?:[^0-9].*)?", re.S)
_DATE_YEAR = re.compile(r"([0-9]{2,4})(?:[^0-9].*)?", re.S)
_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")


def _parse(header: str) -> Optional[Tuple[str, str, _Pairs]]:
    """Name, value and the ordered ``(attribute, value)`` pairs; ``None`` for a header 5.2 ignores."""
    if not isinstance(header, str) or _CTL.search(header):
        return None
    segments = [segment.strip(_WSP) for segment in header.split(";")]
    name, sep, value = segments[0].partition("=")
    name = name.strip(_WSP)
    if not sep or not name:
        return None                      # RFC 6265 5.2 steps 2 and 5: ignore it
    pairs: _Pairs = []
    for segment in segments[1:]:
        key, sep, attr_value = segment.partition("=")
        pairs.append((key.strip(_WSP).lower(), attr_value.strip(_WSP) if sep else ""))
    return name, value.strip(_WSP), pairs


def parse_set_cookie(header: str) -> Optional[Dict[str, Any]]:
    """Parse one ``Set-Cookie`` value into ``{name, value, attributes}``.

    ``attributes`` holds the last value of each attribute; ``None`` means
    RFC 6265 has the header ignored (no ``=``, an empty name, a control
    character).
    """
    parsed = _parse(header)
    if parsed is None:
        return None
    name, value, pairs = parsed
    return {"name": name, "value": value, "attributes": dict(pairs)}


def _classify_date_token(token: str, found: Dict[str, Any]) -> None:
    """RFC 6265 5.1.1 step 2: the first unfilled field ``token`` matches, in order."""
    time_match = _DATE_TIME.fullmatch(token)
    if "time" not in found and time_match:
        found["time"] = tuple(int(part) for part in time_match.groups())
        return
    day_match = _DATE_DAY.fullmatch(token)
    if "day" not in found and day_match:
        found["day"] = int(day_match.group(1))
        return
    if "month" not in found and token[:3].lower() in _MONTHS:
        found["month"] = _MONTHS.index(token[:3].lower()) + 1
        return
    year_match = _DATE_YEAR.fullmatch(token)
    if "year" not in found and year_match:
        found["year"] = int(year_match.group(1))


def _full_year(year: int) -> int:
    if 70 <= year <= 99:
        return year + 1900
    return year + 2000 if year <= 69 else year


def parse_cookie_date(text: str) -> Optional[datetime.datetime]:
    """Parse an ``Expires`` value with the RFC 6265 5.1.1 algorithm; ``None`` if it fails.

    ``email.utils`` read 24 of the http-state date vectors as unparseable
    (``Sat, 15-Apr-17 21:01:22``), took ``69`` for 1969, accepted years before
    1601, and raised ``OverflowError`` for ``12-Aug-9999999999``.
    """
    found: Dict[str, Any] = {}
    for token in _DATE_DELIMITER.split(text or ""):
        if token:
            _classify_date_token(token, found)
    if len(found) < 4:
        return None
    year, (hour, minute, second) = _full_year(found["year"]), found["time"]
    if year < 1601 or hour > 23 or minute > 59 or second > 59:
        return None
    try:            # also step 6: a date that does not exist (31 Feb, day 0 or 32) fails
        return datetime.datetime(year, found["month"], found["day"], hour, minute, second,
                                 tzinfo=datetime.timezone.utc)
    except ValueError:
        return None


def _is_expired(pairs: _Pairs) -> bool:
    """RFC 6265 5.3 step 3: the last *valid* ``Max-Age`` decides, else the last valid ``Expires``.

    An invalid attribute is ignored rather than overriding a valid one before
    it: ``Max-Age=0; Max-Age=abc`` kept the cookie.
    """
    max_ages = [int(value) for key, value in pairs if key == "max-age" and _MAX_AGE.fullmatch(value)]
    if max_ages:
        return max_ages[-1] <= 0
    dates = [parse_cookie_date(value) for key, value in pairs if key == "expires"]
    valid = [when for when in dates if when is not None]
    return bool(valid) and valid[-1] <= datetime.datetime.now(datetime.timezone.utc)


class CookieJar:
    """An in-memory name-value cookie jar (RFC 6265, simplified)."""

    def __init__(self, cookies: Optional[Dict[str, str]] = None) -> None:
        self._cookies: Dict[str, str] = dict(cookies or {})

    def update(self, set_cookie: SetCookie) -> "CookieJar":
        """Apply one or more ``Set-Cookie`` headers to the jar."""
        headers = [set_cookie] if isinstance(set_cookie, str) else set_cookie
        for header in headers:
            self._apply_one(header)
        return self

    def _apply_one(self, header: str) -> None:
        parsed = _parse(header)
        if parsed is None:
            return
        name, value, pairs = parsed
        if _is_expired(pairs):
            self._cookies.pop(name, None)
        else:
            self._cookies[name] = value

    def set(self, name: str, value: str) -> "CookieJar":
        """Set a cookie value directly."""
        self._cookies[str(name)] = str(value)
        return self

    def cookie_header(self) -> str:
        """Build the ``Cookie`` request header value from stored cookies."""
        return "; ".join(f"{name}={value}"
                         for name, value in self._cookies.items())

    def to_dict(self) -> Dict[str, str]:
        """Return the stored cookies as a plain dict."""
        return dict(self._cookies)

    def __len__(self) -> int:
        return len(self._cookies)

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "CookieJar":
        """Build a jar from a plain ``{name: value}`` dict."""
        return cls(data)

    def save(self, path: str) -> str:
        """Persist the jar to ``path`` as JSON; return the path."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(self._cookies, indent=2), encoding="utf-8")
        return str(out)

    @classmethod
    def load(cls, path: str) -> "CookieJar":
        """Load a jar from a JSON file."""
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))
