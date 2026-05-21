"""Test fixtures for the Garmin Coach MCP.

These tests are additive: they import server.py and exercise its pure helpers
to lock in the CURRENT behavior. They never modify server.py, so they cannot
affect what runs in production — they exist precisely so a future cleanup can
be done safely.
"""
import importlib.util
import sys
from pathlib import Path

import pytest
from starlette.requests import Request

ROOT = Path(__file__).resolve().parent.parent  # garmin-coach-mcp/


@pytest.fixture(scope="session")
def server():
    spec = importlib.util.spec_from_file_location("server", ROOT / "server.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["server"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def make_request():
    """Build a minimal Starlette Request for testing request-aware helpers."""
    def _make(path="/", query_string=b"", headers=None, cookies=None):
        raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
        if cookies:
            cookie = "; ".join(f"{k}={v}" for k, v in cookies.items())
            raw.append((b"cookie", cookie.encode()))
        scope = {
            "type": "http",
            "method": "GET",
            "path": path,
            "raw_path": path.encode(),
            "query_string": query_string,
            "headers": raw,
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("test", 12345),
        }
        return Request(scope)
    return _make
