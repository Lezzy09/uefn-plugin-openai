"""Codex sign-in: what the login tab prints, and what `codex login status` says."""

from __future__ import annotations

import subprocess

import codex_auth
from codex_auth import codex_logged_in, parse_login_output

# `codex login --device-auth` (0.163): bold/colour codes around the link and the code.
_DEVICE = (
    "Follow these steps to sign in with ChatGPT using device code authorization:\r\n\r\n"
    "1. Open this link in your browser and sign in to your account\r\n"
    "   \x1b[94mhttps://auth.openai.com/codex/device\x1b[0m\r\n\r\n"
    "2. Enter this one-time code \x1b[90m(expires in 15 minutes)\x1b[0m\r\n"
    "   \x1b[94mABCD-EFG12\x1b[0m\r\n"
)
_BROWSER = (
    "Starting local login server on http://localhost:1455.\r\n"
    "If your browser did not open, navigate to this URL to authenticate:\r\n\r\n"
    "https://auth.openai.com/oauth/authorize?response_type=code&client_id=app_X&state=abc\r\n"
)


def test_device_login_gives_the_link_and_the_code():
    assert parse_login_output(_DEVICE) == {
        "auth_url": "https://auth.openai.com/codex/device",
        "user_code": "ABCD-EFG12",
    }


def test_browser_login_gives_the_link_only():
    got = parse_login_output(_BROWSER)
    assert got["auth_url"].startswith("https://auth.openai.com/oauth/authorize?")
    assert got["auth_url"].endswith("state=abc")
    assert got["user_code"] == ""
    assert parse_login_output("Requesting a one-time code...") == {"auth_url": "", "user_code": ""}


def test_login_status_reads_signed_in_signed_out_and_unknown(monkeypatch):
    def status(out: str, code: int):
        monkeypatch.setattr(codex_auth, "_codex",
                            lambda *_a: subprocess.CompletedProcess([], code, stdout=out, stderr=""))

    status("Logged in using ChatGPT\n", 0)
    assert codex_logged_in() is True
    status("Not logged in\n", 1)
    assert codex_logged_in() is False
    # A crash or garbled answer is not a logout: the turn runs and a real 401 opens Log in.
    status("", 1)
    assert codex_logged_in() is None
    monkeypatch.setattr(codex_auth, "_codex", lambda *_a: None)
    assert codex_logged_in() is None
