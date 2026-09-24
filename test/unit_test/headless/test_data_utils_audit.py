"""Data-utility defects from the 2026-09-24 audit (pure functions; no screen, no network).

A JWT was still accepted at its expiry second, several malformed tokens
raised non-framework errors, and one signature had several valid spellings;
n-gram similarity with n=0 called unrelated strings identical; DAG errors
escaped the framework family; time-series samples sharing a timestamp were
reordered and a mistyped fill was silent; NaN passed range checks; an empty
rollout raised StopIteration; schema checks missed required-only fields and
failed open on an unknown mode; a tiny image raised cv2.error; CSV output
failed on rows with different keys.
"""
import base64
import csv
import json
import math

import numpy as np
import pytest

from je_auto_control.utils.dag.graph import DagDefinitionError
from je_auto_control.utils.data_quality.data_quality import extract_fields, validate_rows
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.feature_flags.feature_flags import Flag, FlagStore, evaluate_flag
from je_auto_control.utils.jwt.jwt_codec import (
    ExpiredTokenError, JwtError, decode_jwt, encode_jwt,
)
from je_auto_control.utils.schema_compat.schema_compat import check_compatibility
from je_auto_control.utils.test_data.test_data import write_dataset
from je_auto_control.utils.text_regions.text_regions import find_text_lines, find_text_regions
from je_auto_control.utils.text_similarity.text_similarity import dice, jaccard, jaro_winkler
from je_auto_control.utils.timeseries.timeseries import ts_increase, ts_resample

KEY = "k" * 32


def _segment(obj) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()


def test_a_jwt_is_rejected_at_its_expiry_second():
    with pytest.raises(ExpiredTokenError):
        decode_jwt(encode_jwt({"exp": 100}, KEY), KEY, now=100)
    assert decode_jwt(encode_jwt({"exp": 100}, KEY), KEY, now=99)["exp"] == 100


def test_malformed_tokens_are_jwt_errors():
    header, _payload, signature = encode_jwt({"a": 1}, KEY).split(".")
    deep = base64.urlsafe_b64encode(b"[" * 100000 + b"]" * 100000).rstrip(b"=").decode()
    for token in (f"{header}.p{chr(0xE9)}.{signature}", f"{deep}.{_segment({})}.{signature}"):
        with pytest.raises(JwtError):
            decode_jwt(token, KEY)
    with pytest.raises(JwtError):
        decode_jwt(encode_jwt({"exp": 10 ** 400}, KEY), KEY, now=0)


def test_a_signature_has_one_spelling():
    token = encode_jwt({"a": 1}, KEY)
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    head, last = token[:-1], token[-1]
    # A 32-byte HS256 signature is 43 characters: the last one carries 2 unused bits.
    twin = head + alphabet[alphabet.index(last) ^ 1]
    assert base64.urlsafe_b64decode(twin.split(".")[2] + "=") == \
        base64.urlsafe_b64decode(token.split(".")[2] + "=")
    with pytest.raises(JwtError):
        decode_jwt(twin, KEY)


def test_similarity_arguments_are_bounded():
    for scorer in (jaccard, dice):
        with pytest.raises(ValueError):
            scorer("abc", "xyz", n=0)
    with pytest.raises(ValueError):
        jaro_winkler("abcd", "abce", prefix_weight=1.0)
    assert jaro_winkler("MARTHA", "MARHTA") == pytest.approx(0.961, abs=1e-3)


def test_dag_errors_are_in_the_framework_family():
    assert issubclass(DagDefinitionError, AutoControlException)
    assert issubclass(DagDefinitionError, ValueError)


def test_samples_sharing_a_timestamp_keep_their_order():
    assert ts_increase([(0, 5), (1, 10), (1, 2), (2, 4)]) == 9.0


@pytest.mark.parametrize("kwargs", [{"fill": "linaer"}, {"bucket_s": math.inf}, {"bucket_s": math.nan}])
def test_resample_rejects_bad_arguments(kwargs):
    arguments = {"bucket_s": 10, **kwargs}
    with pytest.raises(ValueError):
        ts_resample([(0, 1), (15, 2), (30, 3)], arguments.pop("bucket_s"), **arguments)


def test_range_rules_reject_non_finite_numbers_and_unhashables():
    schema = {"x": {"type": "number", "min": 0, "max": 10}, "y": {"allowed": {"a", "b"}}}
    report = validate_rows([{"x": math.nan, "y": "a"}, {"x": math.inf, "y": ["a"]}], schema)
    fields = sorted(error["field"] for error in report["errors"])
    assert fields == ["x", "x", "y"]


def test_extraction_presets_do_not_confuse_dates_addresses_and_phones():
    found = extract_fields("2024-01-15 192.168.1.1 999.999.999.999 +1 (555) 123-4567",
                           ["ipv4", "phone"])
    assert found == {"ipv4": ["192.168.1.1"], "phone": ["+1 (555) 123-4567"]}


def test_malformed_serves_fall_back_to_the_default_variant():
    variants = {"on": True, "off": False}
    store = FlagStore({
        "empty": Flag("empty", variants, default_variant="off", fallthrough={"rollout": {}}),
        "named": Flag("named", variants, default_variant="off", fallthrough={"variant": "on"}),
    })
    assert evaluate_flag(store, "empty")["variant"] == "off"
    assert evaluate_flag(store, "empty")["reason"] == "ERROR"
    assert evaluate_flag(store, "named")["value"] is True


def test_schema_compat_sees_required_only_fields_and_rejects_unknown_modes():
    report = check_compatibility({"type": "object"}, {"type": "object", "required": ["x"]})
    assert report["compatible"] is False
    with pytest.raises(ValueError):
        check_compatibility({"type": "string"}, {"type": "integer"}, mode="Backward")


@pytest.mark.parametrize("finder", [find_text_regions, find_text_lines])
def test_a_tiny_image_is_contained(finder):
    try:
        assert finder(np.zeros((1, 1), np.uint8)) == []
    except AutoControlException:
        pass


def test_csv_rows_with_different_keys(tmp_path):
    target = tmp_path / "rows.csv"
    write_dataset([{"a": 1}, {"b": 2}], str(target))
    with target.open(encoding="utf-8", newline="") as handle:
        assert list(csv.DictReader(handle)) == [{"a": "1", "b": ""}, {"a": "", "b": "2"}]
