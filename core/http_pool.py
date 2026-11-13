"""Keep-alive HTTP for outbound API calls (Telegram Bot API first of all).

`requests.post(...)` opens a fresh TCP + TLS connection every time: from the
production server that is ~120 ms per Telegram call against ~20 ms on a
reused connection, and one bot tap makes 3-5 calls. `post()` / `get()` here
have the same signature but go through a per-thread pooled Session.

Tests keep working unchanged: when `requests.post` / `requests.get` has been
patched (mock.patch("requests.post") or "<module>.requests.post", which is
the same attribute), the call goes to the patched function instead.
"""
from __future__ import annotations

import threading

import requests
from requests.adapters import HTTPAdapter

_ORIGINAL_POST = requests.post
_ORIGINAL_GET = requests.get
_local = threading.local()


def session() -> requests.Session:
    s = getattr(_local, "session", None)
    if s is None:
        s = requests.Session()
        adapter = HTTPAdapter(pool_connections=8, pool_maxsize=16, max_retries=0)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _local.session = s
    return s


def post(url: str, **kwargs) -> requests.Response:
    if requests.post is not _ORIGINAL_POST:  # patched by a test
        return requests.post(url, **kwargs)
    return session().post(url, **kwargs)


def get(url: str, **kwargs) -> requests.Response:
    if requests.get is not _ORIGINAL_GET:  # patched by a test
        return requests.get(url, **kwargs)
    return session().get(url, **kwargs)
