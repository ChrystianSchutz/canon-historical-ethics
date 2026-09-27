"""Inspect model providers that run a model through its vendor CLI instead of an API key.

    --model claudecli/sonnet                     # `claude -p` (Claude Code credits)
    --model codexcli/gpt-5.6-sol -M effort=low   # `codex exec` (Codex plan)

Registered through the ``inspect_ai`` entry point in ``pyproject.toml``.

Multi-turn conversations map to one CLI session each. After every reply the provider stores the
session id under a digest of the transcript so far. The next turn resumes that session and sends
only the new user message, so the model sees a real multi-turn conversation.

Confounds compared with a bare API call (report them with any result obtained this way):

- claude: runs with ``--safe-mode``, no tools and a replaced system prompt, but Claude Code still
  adds a short system reminder (environment, date, account e-mail).
- codex: Codex's agent instructions (about 17k tokens) are always present and cannot be replaced.
  Each resumed turn re-sends the history, so cost grows quickly with conversation length.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from inspect_ai.model import (
    ChatMessage,
    ChatMessageAssistant,
    ChatMessageSystem,
    GenerateConfig,
    ModelAPI,
    ModelOutput,
    ModelUsage,
    modelapi,
)
from inspect_ai.tool import ToolChoice, ToolInfo
from inspect_ai.util import store

DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."
TIMEOUT_SECONDS = 900
# Key under which a conversation's CLI session id is kept in its own sample store.
SESSION_KEY = "canon_cli_session"


def transcript_digest(messages: list[ChatMessage]) -> str:
    digest = hashlib.sha256()
    for message in messages:
        digest.update(message.role.encode("utf-8"))
        digest.update(b"\x1f")
        digest.update(message.text.encode("utf-8"))
        digest.update(b"\x1e")
    return digest.hexdigest()


def split_conversation(
    messages: list[ChatMessage],
) -> tuple[str | None, list[ChatMessage], ChatMessage]:
    """(system prompt, earlier turns, the new user message)."""
    system = "\n\n".join(m.text for m in messages if isinstance(m, ChatMessageSystem)) or None
    conversation: list[ChatMessage] = [m for m in messages if not isinstance(m, ChatMessageSystem)]
    if not conversation or conversation[-1].role != "user":
        raise ValueError("the last message sent to a CLI model must come from the user")
    return system, conversation[:-1], conversation[-1]


def _int(value: Any) -> int:
    return int(value) if value is not None else 0


def parse_claude_json(stdout: str) -> tuple[str, str, ModelUsage]:
    """(reply, session id, usage) from ``claude -p --output-format json``."""
    line = next(ln for ln in reversed(stdout.splitlines()) if ln.strip().startswith("{"))
    data = json.loads(line)
    if data.get("is_error"):
        raise RuntimeError(f"claude reported an error: {str(data.get('result'))[:500]}")
    usage = data.get("usage") or {}
    input_tokens = _int(usage.get("input_tokens"))
    output_tokens = _int(usage.get("output_tokens"))
    return (
        str(data.get("result") or ""),
        str(data["session_id"]),
        ModelUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            input_tokens_cache_read=usage.get("cache_read_input_tokens"),
            input_tokens_cache_write=usage.get("cache_creation_input_tokens"),
            reasoning_tokens=(usage.get("output_tokens_details") or {}).get("thinking_tokens"),
            total_cost=data.get("total_cost_usd"),
        ),
    )


def parse_codex_events(stdout: str) -> tuple[str, str | None, ModelUsage]:
    """(reply, thread id or None on resume, usage) from ``codex exec --json``."""
    thread: str | None = None
    replies: list[str] = []
    usage: dict[str, Any] = {}
    for raw in stdout.splitlines():
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        if kind == "thread.started":
            thread = event.get("thread_id")
        elif kind == "item.completed" and (event.get("item") or {}).get("type") == "agent_message":
            replies.append(str(event["item"].get("text") or ""))
        elif kind == "turn.completed":
            usage = event.get("usage") or {}
        elif kind in {"error", "turn.failed"}:
            raise RuntimeError(f"codex reported an error: {json.dumps(event)[:500]}")
    if not replies:
        raise RuntimeError("codex returned no agent message")
    input_tokens = _int(usage.get("input_tokens"))
    output_tokens = _int(usage.get("output_tokens"))
    return (
        replies[-1],
        thread,
        ModelUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            input_tokens_cache_read=usage.get("cached_input_tokens"),
            reasoning_tokens=usage.get("reasoning_output_tokens"),
        ),
    )


async def _run(command: list[str], stdin: str, cwd: Path) -> str:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    try:
        out, err = await asyncio.wait_for(
            process.communicate(stdin.encode("utf-8")), TIMEOUT_SECONDS
        )
    except TimeoutError:
        process.kill()
        raise
    if process.returncode != 0:
        tail = err.decode("utf-8", "replace")[-800:]
        raise RuntimeError(f"{Path(command[0]).name} exited {process.returncode}: {tail}")
    return out.decode("utf-8", "replace")


class _CliModelAPI(ModelAPI):
    executable_name = ""

    def __init__(
        self,
        model_name: str,
        base_url: str | None = None,
        api_key: str | None = None,
        config: GenerateConfig = GenerateConfig(),  # noqa: B008
        **model_args: Any,
    ) -> None:
        super().__init__(model_name=model_name, base_url=base_url, api_key=api_key, config=config)
        executable = shutil.which(self.executable_name)
        if executable is None:
            raise RuntimeError(f"`{self.executable_name}` is not on PATH")
        self.executable = executable
        self.model_args = model_args
        # An empty working directory keeps project instructions (CLAUDE.md, AGENTS.md) out.
        self.workdir = Path(tempfile.mkdtemp(prefix="canon-cli-"))

    def max_connections(self) -> int:
        return int(self.model_args.get("max_connections", 4))

    async def call(
        self, prompt: str, system: str | None, session: str | None
    ) -> tuple[str, str | None, ModelUsage]:
        raise NotImplementedError

    async def generate(
        self,
        input: list[ChatMessage],
        tools: list[ToolInfo],
        tool_choice: ToolChoice,
        config: GenerateConfig,
    ) -> ModelOutput:
        if tools:
            raise ValueError("CLI model providers do not support tools")
        system, earlier, user = split_conversation(input)
        # The session id lives in *this conversation's* sample store, so it can never be handed
        # to another conversation. Keying it by transcript content instead was a real defect:
        # replicates of one dialogue open identically, so their digests collide, and they then
        # resumed one another's CLI session. Once their answers diverged the provider rejected
        # the inconsistent resume (observed as a 403 around turn 7 of 22).
        conversation = store()
        session: str | None = None
        if earlier:
            record = conversation.get(SESSION_KEY)
            digest = transcript_digest(earlier)
            if not record or record.get("digest") != digest:
                raise RuntimeError(
                    "no CLI session matches this conversation; turns must run in order, and "
                    "each conversation needs its own sample store"
                )
            session = str(record["session"])
        reply, new_session, usage = await self.call(user.text, system, session)
        session = new_session or session
        if session is not None:
            conversation.set(
                SESSION_KEY,
                {
                    "session": session,
                    "digest": transcript_digest(
                        [*earlier, user, ChatMessageAssistant(content=reply)]
                    ),
                },
            )
        output = ModelOutput.from_content(model=self.model_name, content=reply)
        output.usage = usage
        return output


class ClaudeCliAPI(_CliModelAPI):
    executable_name = "claude"

    async def call(
        self, prompt: str, system: str | None, session: str | None
    ) -> tuple[str, str | None, ModelUsage]:
        command = [
            self.executable,
            "-p",
            "--model",
            self.model_name,
            "--output-format",
            "json",
            "--tools",
            "",
            "--strict-mcp-config",
            "--safe-mode",
            "--system-prompt",
            system or DEFAULT_SYSTEM_PROMPT,
        ]
        if "effort" in self.model_args:
            command += ["--effort", str(self.model_args["effort"])]
        if session is not None:
            command += ["--resume", session]
        return parse_claude_json(await _run(command, prompt, self.workdir))


class CodexCliAPI(_CliModelAPI):
    executable_name = "codex"

    async def call(
        self, prompt: str, system: str | None, session: str | None
    ) -> tuple[str, str | None, ModelUsage]:
        options = [
            "--json",
            "--skip-git-repo-check",
            "-m",
            self.model_name,
            "-c",
            f"model_reasoning_effort={self.model_args.get('effort', 'low')}",
            "-c",
            "sandbox_mode=read-only",
        ]
        text = f"{system}\n\n{prompt}" if system and session is None else prompt
        if session is None:
            command = [self.executable, "exec", *options, "-"]
        else:
            command = [self.executable, "exec", "resume", *options, session, "-"]
        return parse_codex_events(await _run(command, text, self.workdir))


@modelapi(name="claudecli")
def claudecli() -> type[ModelAPI]:
    return ClaudeCliAPI


@modelapi(name="codexcli")
def codexcli() -> type[ModelAPI]:
    return CodexCliAPI
