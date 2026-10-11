"""Logging in to online models. Always through the default web browser.

Keys live only in memory (Session) until the program closes; nothing is
written to disk, so the login is repeated on every start.
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import secrets
import socket
import threading
import urllib.parse
import webbrowser

import httpx

from .providers.base import ProviderSpec


class Session:
    """In-memory logins for this run of the program."""

    def __init__(self):
        self._keys: dict[str, str] = {}

    def set(self, provider_id: str, key: str) -> None:
        self._keys[provider_id] = key.strip()

    def get(self, provider_id: str) -> str | None:
        return self._keys.get(provider_id)

    def logged_in(self, provider_id: str) -> bool:
        return provider_id in self._keys

    def forget(self, provider_id: str) -> None:
        self._keys.pop(provider_id, None)


def open_browser(url: str) -> bool:
    return webbrowser.open(url, new=2)


def open_key_page(spec: ProviderSpec) -> bool:
    """For providers that only issue API keys: open the key page; the user pastes the key."""
    if not spec.key_url:
        raise ValueError(f"{spec.label} has no key page")
    return open_browser(spec.key_url)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_PAGE = ("<html><body style='font-family:sans-serif;padding:3em'><h2>Divide Reader</h2>"
         "<p>{msg}</p><p>You can close this tab.</p></body></html>")


def openrouter_login(timeout: float = 300.0, cancel: threading.Event | None = None) -> str:
    """OAuth PKCE: browser login on openrouter.ai, key comes back to a localhost callback."""
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    port = _free_port()
    got: dict[str, str] = {}
    done = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            ok = q.get("state", [""])[0] == state and "code" in q
            if ok:
                got["code"] = q["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "Login received." if ok else "Login failed or was cancelled."
            self.wfile.write(_PAGE.format(msg=msg).encode())
            if ok:
                done.set()

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", port), Handler)
    server.timeout = 1
    callback = f"http://localhost:{port}/callback"
    url = "https://openrouter.ai/auth?" + urllib.parse.urlencode({
        "callback_url": callback, "code_challenge": challenge, "code_challenge_method": "S256",
        "state": state, "key_label": "Divide Reader"})
    open_browser(url)
    waited = 0.0
    try:
        while not done.is_set() and waited < timeout:
            if cancel is not None and cancel.is_set():
                raise InterruptedError("login cancelled")
            server.handle_request()
            waited += 1
    finally:
        server.server_close()
    if "code" not in got:
        raise TimeoutError("no login received from OpenRouter")
    r = httpx.post("https://openrouter.ai/api/v1/auth/keys", timeout=30,
                   json={"code": got["code"], "code_verifier": verifier, "code_challenge_method": "S256"})
    r.raise_for_status()
    return r.json()["key"]
