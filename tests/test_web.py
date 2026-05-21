"""Web-layer helpers: URL building, password field, and auth gating."""


def test_public_base_url_honors_proxy_headers(server, make_request):
    req = make_request(headers={
        "x-forwarded-proto": "https",
        "x-forwarded-host": "foo.up.railway.app",
    })
    assert server._public_base_url(req) == "https://foo.up.railway.app"


def test_public_base_url_fallback_to_host(server, make_request):
    req = make_request(headers={"host": "bar.example:80"})
    assert server._public_base_url(req) == "http://bar.example:80"


def test_request_is_https(server, make_request):
    assert server._request_is_https(make_request(headers={"x-forwarded-proto": "https"})) is True
    assert server._request_is_https(make_request(headers={"x-forwarded-proto": "http"})) is False


def test_railway_deep_link_none_without_ids(server, monkeypatch):
    monkeypatch.setattr(server, "RAILWAY_PROJECT_ID", "")
    monkeypatch.setattr(server, "RAILWAY_SERVICE_ID", "")
    assert server._railway_variables_deep_link() is None


def test_railway_deep_link_built_with_ids(server, monkeypatch):
    monkeypatch.setattr(server, "RAILWAY_PROJECT_ID", "P")
    monkeypatch.setattr(server, "RAILWAY_SERVICE_ID", "S")
    monkeypatch.setattr(server, "RAILWAY_ENVIRONMENT_ID", "E")
    url = server._railway_variables_deep_link()
    assert "project/P" in url
    assert "service/S" in url
    assert "environmentId=E" in url


def test_password_input_is_hidden_with_eye_toggle(server):
    html = server._password_input_html("pwd", "pwd", placeholder="x", minlength=8)
    assert 'type="password"' in html      # hidden by default
    assert "pw-toggle" in html            # eye toggle present
    assert 'minlength="8"' in html
    assert 'placeholder="x"' in html


def test_login_open_when_no_password_set(server, monkeypatch, make_request):
    monkeypatch.setattr(server, "_current_admin_token", lambda: "")
    assert server._login_admin_ok(make_request()) is True


def test_login_requires_password_when_set(server, monkeypatch, make_request):
    monkeypatch.setattr(server, "_current_admin_token", lambda: "secret")
    assert server._login_admin_ok(make_request()) is False
    assert server._login_admin_ok(make_request(query_string=b"token=secret")) is True
    assert server._login_admin_ok(make_request(cookies={"admin_token": "secret"})) is True
    assert server._login_admin_ok(make_request(query_string=b"token=wrong")) is False
