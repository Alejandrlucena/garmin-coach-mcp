"""Behavior of pure helper functions — locks in CURRENT behavior."""
import base64

import pytest


def test_safe_float_behavior(server):
    f = server._safe_float
    assert f("") is None
    assert f(None) is None
    assert f("abc") is None
    assert f(3.5) == 3.5
    assert f("3.5") == 3.5
    # The effective (last) definition does NOT special-case bools:
    assert f(True) == 1.0


def test_translate_garmin(server):
    t = server._translate_garmin
    assert t("BALANCED") == "Equilibrado"
    assert t("PRODUCTIVE") == "Productivo"
    # Unknown values pass through unchanged.
    assert t("xyz") == "xyz"


def test_human_time_ago(server):
    h = server._human_time_ago
    assert h(None) == "nunca"
    assert h(0) == "hace segundos"
    assert h(5) == "hace 5 min"
    assert h(70) == "hace 1 h"
    assert h(3000) == "hace 2 d"


def test_json_loads_maybe_base64(server):
    j = server._json_loads_maybe_base64
    assert j('{"a": 1}') == {"a": 1}
    assert j(base64.b64encode(b'{"a": 2}').decode()) == {"a": 2}


def test_json_loads_maybe_base64_invalid_raises(server):
    with pytest.raises(Exception):
        server._json_loads_maybe_base64("%%% not json %%%")
