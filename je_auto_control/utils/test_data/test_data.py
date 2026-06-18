"""Seeded synthetic test-data generator (pure standard library).

Generate deterministic fake rows from a tiny field schema, to drive
data-driven runs (``AC_load_data`` / :mod:`data_source`) without shipping
real PII. No third-party dependency (no Faker): a curated word/name pool
plus the stdlib :class:`random.Random` keep output reproducible for a
given ``seed`` so test runs stay stable.

A schema maps each field name to a *spec* — either a bare type name or a
``{"type": ..., **params}`` mapping::

    from je_auto_control import generate_rows

    rows = generate_rows({
        "name": "name",
        "email": {"type": "email", "domain": "acme.test"},
        "age": {"type": "int", "min": 18, "max": 65},
        "status": {"type": "choice", "choices": ["new", "vip"]},
    }, count=100, seed=7)

The same ``seed`` always yields the same rows.
"""
import csv
import json
import random
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

_FIRST = ("Alex", "Sam", "Jordan", "Taylor", "Morgan", "Casey", "Riley",
          "Jamie", "Avery", "Quinn", "Drew", "Cameron", "Skyler", "Reese",
          "Rowan", "Sage")
_LAST = ("Chen", "Smith", "Lee", "Garcia", "Patel", "Kim", "Nguyen", "Brown",
         "Muller", "Rossi", "Tanaka", "Silva", "Khan", "Novak", "Haddad",
         "Owusu")
_CITY = ("Taipei", "Berlin", "Lisbon", "Osaka", "Nairobi", "Lima", "Oslo",
         "Cairo", "Toronto", "Pune", "Bogota", "Hanoi")
_WORDS = ("alpha", "beta", "gamma", "delta", "orbit", "river", "stone",
          "ember", "quartz", "willow", "harbor", "meadow", "cobalt", "ivory",
          "cedar", "onyx")
_SUFFIX = ("Labs", "Group", "Systems", "Works", "Co")
_DOMAINS = ("example.com", "test.org", "sample.net")


def _g_first(rng: random.Random, _spec: Dict[str, Any]) -> str:
    return rng.choice(_FIRST)


def _g_last(rng: random.Random, _spec: Dict[str, Any]) -> str:
    return rng.choice(_LAST)


def _g_name(rng: random.Random, _spec: Dict[str, Any]) -> str:
    return f"{rng.choice(_FIRST)} {rng.choice(_LAST)}"


def _g_word(rng: random.Random, _spec: Dict[str, Any]) -> str:
    return rng.choice(_WORDS)


def _g_city(rng: random.Random, _spec: Dict[str, Any]) -> str:
    return rng.choice(_CITY)


def _g_company(rng: random.Random, _spec: Dict[str, Any]) -> str:
    return f"{rng.choice(_WORDS).capitalize()} {rng.choice(_SUFFIX)}"


def _g_username(rng: random.Random, _spec: Dict[str, Any]) -> str:
    return f"{rng.choice(_FIRST).lower()}{rng.randint(1, 9999)}"


def _g_email(rng: random.Random, spec: Dict[str, Any]) -> str:
    domain = spec.get("domain") or rng.choice(_DOMAINS)
    return (f"{rng.choice(_FIRST).lower()}.{rng.choice(_LAST).lower()}"
            f"{rng.randint(1, 999)}@{domain}")


def _g_phone(rng: random.Random, _spec: Dict[str, Any]) -> str:
    return (f"+1-{rng.randint(200, 999)}-{rng.randint(200, 999)}-"
            f"{rng.randint(1000, 9999)}")


def _g_uuid(rng: random.Random, _spec: Dict[str, Any]) -> str:
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def _g_bool(rng: random.Random, spec: Dict[str, Any]) -> bool:
    return rng.random() < float(spec.get("p", 0.5))


def _g_int(rng: random.Random, spec: Dict[str, Any]) -> int:
    return rng.randint(int(spec.get("min", 0)), int(spec.get("max", 100)))


def _g_float(rng: random.Random, spec: Dict[str, Any]) -> float:
    value = rng.uniform(float(spec.get("min", 0.0)),
                        float(spec.get("max", 1.0)))
    return round(value, int(spec.get("ndigits", 2)))


def _g_choice(rng: random.Random, spec: Dict[str, Any]) -> Any:
    choices = list(spec.get("choices") or [""])
    return rng.choice(choices)


def _g_sentence(rng: random.Random, spec: Dict[str, Any]) -> str:
    count = max(1, int(spec.get("words", 6)))
    body = " ".join(rng.choice(_WORDS) for _ in range(count))
    return f"{body.capitalize()}."


def _parse_date(raw: Optional[str], fallback: date) -> date:
    if not raw:
        return fallback
    return date.fromisoformat(str(raw))


def _g_date(rng: random.Random, spec: Dict[str, Any]) -> str:
    start = _parse_date(spec.get("start"), date(2000, 1, 1))
    end = _parse_date(spec.get("end"), date.today())
    span = max(0, (end - start).days)
    return (start + timedelta(days=rng.randint(0, span))).isoformat()


_GENERATORS: Dict[str, Callable[[random.Random, Dict[str, Any]], Any]] = {
    "first_name": _g_first, "last_name": _g_last, "name": _g_name,
    "word": _g_word, "city": _g_city, "company": _g_company,
    "username": _g_username, "email": _g_email, "phone": _g_phone,
    "uuid": _g_uuid, "bool": _g_bool, "int": _g_int, "float": _g_float,
    "choice": _g_choice, "sentence": _g_sentence, "date": _g_date,
}


def field_types() -> List[str]:
    """Return the sorted list of supported field-type names."""
    return sorted(_GENERATORS)


def _normalize(field: str, spec: Any) -> Dict[str, Any]:
    if isinstance(spec, str):
        spec = {"type": spec}
    if not isinstance(spec, dict) or "type" not in spec:
        raise ValueError(
            f"field {field!r}: spec must be a type name or {{'type': ...}}")
    kind = spec["type"]
    if kind not in _GENERATORS:
        raise ValueError(
            f"field {field!r}: unknown type {kind!r}; "
            f"known: {sorted(_GENERATORS)}")
    return spec


def _make_row(rng: random.Random,
              specs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    return {field: _GENERATORS[spec["type"]](rng, spec)
            for field, spec in specs.items()}


def generate_rows(schema: Dict[str, Any], count: int, *,
                  seed: Optional[int] = None) -> List[Dict[str, Any]]:
    """Return ``count`` deterministic rows matching ``schema``.

    ``schema`` maps each field name to a type name (e.g. ``"email"``) or a
    ``{"type": ..., **params}`` mapping. The same ``seed`` always yields
    identical rows.
    """
    if not isinstance(schema, dict) or not schema:
        raise ValueError("schema must be a non-empty {field: spec} mapping")
    rng = random.Random(seed)  # nosec B311  # reason: non-crypto test data
    specs = {field: _normalize(field, spec) for field, spec in schema.items()}
    return [_make_row(rng, specs) for _ in range(max(0, int(count)))]


def write_dataset(rows: List[Dict[str, Any]], path: str,
                  fmt: Optional[str] = None) -> str:
    """Write ``rows`` to ``path`` as JSON or CSV; return the resolved path.

    ``fmt`` defaults to the file extension (``.json`` or ``.csv``).
    """
    target = Path(path)
    chosen = (fmt or target.suffix.lstrip(".") or "json").lower()
    if chosen == "json":
        target.write_text(json.dumps(rows, indent=2, ensure_ascii=False),
                          encoding="utf-8")
    elif chosen == "csv":
        _write_csv(rows, target)
    else:
        raise ValueError(f"unsupported format {chosen!r}; use 'json' or 'csv'")
    return str(target.resolve())


def _write_csv(rows: List[Dict[str, Any]], target: Path) -> None:
    fields = list(rows[0].keys()) if rows else []
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
