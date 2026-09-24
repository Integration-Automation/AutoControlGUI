"""``AC_jwt_decode`` accepts ``algorithms`` as one name, a JSON list or a list (fake key)."""
import pytest

from je_auto_control.utils.executor.action_executor import _jwt_decode
from je_auto_control.utils.jwt import encode_jwt

KEY = "test-secret-1"


@pytest.mark.parametrize("algorithms", ["HS256", '["HS256"]', ["HS256"], None])
def test_algorithms_in_every_spelling(algorithms):
    token = encode_jwt({"sub": "a"}, KEY)
    assert _jwt_decode(token, KEY, algorithms=algorithms) == {"ok": True, "claims": {"sub": "a"}}


def test_a_name_outside_the_token_algorithm_still_fails_closed():
    token = encode_jwt({"sub": "a"}, KEY)
    assert _jwt_decode(token, KEY, algorithms="HS512")["ok"] is False
