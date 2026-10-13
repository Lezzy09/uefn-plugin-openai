from __future__ import annotations

import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
for k in list(sys.modules):
    if k == "backend" or k.startswith("backend."):
        del sys.modules[k]
for p in _here.parents:
    cand = p / "UEFN-Ducky-Release" / "ducky_app"
    if (cand / "backend" / "agent").is_dir():
        sys.path.insert(0, str(_here))
        sys.path.insert(0, str(cand))
        break

from backend.agent.providers.base import ProviderMessage, ToolCallRequest
from openai_provider import OpenAIProvider


def test_followup_comes_after_previous_reply():
    msgs = [
        ProviderMessage(role="user", content="first"),
        ProviderMessage(
            role="assistant",
            content="Checking",
            tool_calls=[ToolCallRequest(id="t1", name="ping", arguments={})],
        ),
        ProviderMessage(role="tool", tool_call_id="t1", content='{"ok":true}'),
        ProviderMessage(role="assistant", content="Here is the answer."),
        ProviderMessage(role="user", content="follow up"),
    ]
    out = OpenAIProvider("k", "gpt-4o")._to_openai_messages("sys", msgs)
    roles = [m["role"] for m in out if m["role"] != "system"]
    assert roles == ["user", "assistant", "tool", "assistant", "user"]
    assert out[-2]["content"] == "Here is the answer."
    assert out[-1]["content"] == "follow up"


def _reasoning_loop() -> list[ProviderMessage]:
    return [
        ProviderMessage(role="user", content="wire the device"),
        ProviderMessage(
            role="assistant",
            content="",
            thinking="The spawner is not wired yet, so read status first.",
            tool_calls=[ToolCallRequest(id="t1", name="ducky_get_status", arguments={})],
        ),
        ProviderMessage(role="tool", tool_call_id="t1", content='{"ok":true}'),
        ProviderMessage(role="assistant", content="Done.", thinking="Status was fine."),
    ]


def test_reasoning_never_goes_to_openai_proper(monkeypatch):
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    out = OpenAIProvider("k", "gpt-4o")._to_openai_messages("sys", _reasoning_loop())
    assert all("reasoning_content" not in m and "reasoning" not in m for m in out)


def test_reasoning_content_replays_on_a_compatible_endpoint(monkeypatch):
    # DeepSeek's thinking mode 400s when a tool-call turn comes back without it.
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
    out = OpenAIProvider("k", "deepseek-reasoner")._to_openai_messages("sys", _reasoning_loop())
    step, final = out[2], out[4]
    assert step["role"] == "assistant" and step["tool_calls"]
    assert step["reasoning_content"] == "The spawner is not wired yet, so read status first."
    assert final["reasoning_content"] == "Status was fine."
    assert "reasoning_content" not in out[1] and "reasoning_content" not in out[3]  # user, tool
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    out = OpenAIProvider("k", "gpt-4o")._to_openai_messages("sys", _reasoning_loop())
    assert all("reasoning_content" not in m for m in out)
