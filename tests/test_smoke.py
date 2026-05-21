"""Smoke tests: the module must import cleanly and expose its core objects."""


def test_module_imports_and_mcp_exists(server):
    assert server.mcp is not None
    assert type(server.mcp).__name__ == "FastMCP"


def test_core_helpers_exist(server):
    for name in [
        "_safe_float",
        "_translate_garmin",
        "_json_loads_maybe_base64",
        "_human_time_ago",
        "_railway_variables_deep_link",
        "_public_base_url",
        "_request_is_https",
        "_password_input_html",
        "_login_admin_ok",
        "_current_admin_token",
        "_collect_day_snapshot",
        "_normalize_activity",
        "_update_railway_variable_with_token",
    ]:
        assert callable(getattr(server, name)), f"missing/non-callable: {name}"
