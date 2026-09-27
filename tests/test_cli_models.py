"""CLI model providers: deterministic parts only (no CLI is called)."""

from __future__ import annotations

import json

import pytest
from inspect_ai.model import ChatMessageAssistant, ChatMessageSystem, ChatMessageUser

from canon.inspect_adapter.cli_models import (
    parse_claude_json,
    parse_codex_events,
    split_conversation,
    transcript_digest,
)


def test_transcript_digest_is_stable_and_order_sensitive() -> None:
    a = [ChatMessageUser(content="hi"), ChatMessageAssistant(content="OK")]
    b = [ChatMessageUser(content="hi"), ChatMessageAssistant(content="OK")]
    assert transcript_digest(a) == transcript_digest(b)
    assert transcript_digest(a) != transcript_digest(list(reversed(a)))


def test_split_conversation_separates_system_history_and_new_message() -> None:
    messages = [
        ChatMessageSystem(content="sys"),
        ChatMessageUser(content="one"),
        ChatMessageAssistant(content="reply"),
        ChatMessageUser(content="two"),
    ]
    system, earlier, user = split_conversation(messages)
    assert system == "sys"
    assert [m.text for m in earlier] == ["one", "reply"]
    assert user.text == "two"
    with pytest.raises(ValueError):
        split_conversation([ChatMessageAssistant(content="x")])


def test_parse_claude_json() -> None:
    payload = {
        "is_error": False,
        "result": "17",
        "session_id": "abc",
        "total_cost_usd": 0.002,
        "usage": {
            "input_tokens": 900,
            "output_tokens": 4,
            "cache_read_input_tokens": 10,
            "output_tokens_details": {"thinking_tokens": 0},
        },
    }
    text, session, usage = parse_claude_json("noise\n" + json.dumps(payload))
    assert (text, session) == ("17", "abc")
    assert usage.total_tokens == 904 and usage.total_cost == 0.002


def test_parse_codex_events() -> None:
    events = [
        {"type": "thread.started", "thread_id": "t-1"},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"id": "i0", "type": "agent_message", "text": "OK"}},
        {
            "type": "turn.completed",
            "usage": {"input_tokens": 17006, "cached_input_tokens": 11392, "output_tokens": 5},
        },
    ]
    stdout = "Reading additional input from stdin...\n" + "\n".join(json.dumps(e) for e in events)
    text, thread, usage = parse_codex_events(stdout)
    assert (text, thread) == ("OK", "t-1")
    assert usage.input_tokens == 17006 and usage.input_tokens_cache_read == 11392
    with pytest.raises(RuntimeError):
        parse_codex_events(json.dumps({"type": "turn.started"}))
