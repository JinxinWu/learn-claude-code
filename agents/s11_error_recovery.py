#!/usr/bin/env python3
# Harness: resilience -- a robust agent recovers instead of crashing.
"""
s11_error_recovery.py - Error Recovery
Teaching demo of three recovery paths:
- continue when output is truncated
- compact when context grows too large
- back off when transport errors are temporary
    LLM response
         |
         v
    [Check stop_reason]
         |
         +-- "max_tokens" ----> [Strategy 1: max_output_tokens recovery]
         |                       Inject continuation message:
         |                       "Output limit hit. Continue directly."
         |                       Retry up to MAX_RECOVERY_ATTEMPTS (3).
         |                       Counter: max_output_recovery_count
         |
         +-- API error -------> [Check error type]
         |                       |
         |                       +-- prompt_too_long --> [Strategy 2: compact + retry]
         |                       |   Trigger auto_compact (LLM summary).
         |                       |   Replace history with summary.
         |                       |   Retry the turn.
         |                       |
         |                       +-- connection/rate --> [Strategy 3: backoff retry]
         |                           Exponential backoff: base * 2^attempt + jitter
         |                           Up to 3 retries.
         |
         +-- "end_turn" -----> [Normal exit]
    Recovery priority (first match wins):
    1. max_tokens -> inject continuation, retry
    2. prompt_too_long -> compact, retry
    3. connection error -> backoff, retry
    4. all retries exhausted -> fail gracefully
"""
import json
import os
import random
import subprocess
import time
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv


load_dotenv(override=True)

WORKDIR = Path.cwd()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise RuntimeError("OPENAI_API_KEY is required")

client = OpenAI(
    api_key=api_key,
    base_url=os.getenv("OPENAI_BASE_URL"),
)
MODEL = os.environ["MODEL_ID"]
# Recovery constants
MAX_RECOVERY_ATTEMPTS = 3
BACKOFF_BASE_DELAY = 1.0  # seconds
BACKOFF_MAX_DELAY = 30.0  # seconds
TOKEN_THRESHOLD = 50000   # chars / 4 ~ tokens for compact trigger
CONTINUATION_MESSAGE = (
    "Output limit hit. Continue directly from where you stopped -- "
    "no recap, no repetition. Pick up mid-sentence if needed."
)


def estimate_tokens(messages: list) -> int:
    """Rough token estimate: ~4 chars per token."""
    return len(json.dumps(messages, default=str)) // 4


def auto_compact(messages: list) -> list:
    """
    Compress conversation history into a short continuation summary.
    """
    conversation_text = json.dumps(messages, default=str)[:80000]
    prompt = (
        "Summarize this conversation for continuity. Include:\n"
        "1) Task overview and success criteria\n"
        "2) Current state: completed work, files touched\n"
        "3) Key decisions and failed approaches\n"
        "4) Remaining next steps\n"
        "Be concise but preserve critical details.\n\n"
        + conversation_text
    )
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000,
        )
        summary = response.choices[0].message.content or ""
    except Exception as e:
        summary = f"(compact failed: {e}). Previous context lost."
    continuation = (
        "This session continues from a previous conversation that was compacted. "
        f"Summary of prior context:\n\n{summary}\n\n"
        "Continue from where we left off without re-asking the user."
    )
    return [{"role": "user", "content": continuation}]


def backoff_delay(attempt: int) -> float:
    """Exponential backoff with jitter: base * 2^attempt + random(0, 1)."""
    delay = min(BACKOFF_BASE_DELAY * (2 ** attempt), BACKOFF_MAX_DELAY)
    jitter = random.uniform(0, 1)
    return delay + jitter


# -- Tool implementations --
def safe_path(p: str) -> Path:
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path


def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"
    try:
        r = subprocess.run(command, shell=True, cwd=WORKDIR,
                           capture_output=True, text=True, timeout=120)
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"


def run_read(path: str, limit: int = None) -> str:
    try:
        lines = safe_path(path).read_text().splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more)"]
        return "\n".join(lines)[:50000]
    except Exception as e:
        return f"Error: {e}"


def run_write(path: str, content: str) -> str:
    try:
        fp = safe_path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content)
        return f"Wrote {len(content)} bytes"
    except Exception as e:
        return f"Error: {e}"


def run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        fp = safe_path(path)
        content = fp.read_text()
        if old_text not in content:
            return f"Error: Text not found in {path}"
        fp.write_text(content.replace(old_text, new_text, 1))
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"


TOOL_HANDLERS = {
    "bash":       lambda **kw: run_bash(kw["command"]),
    "read_file":  lambda **kw: run_read(kw["path"], kw.get("limit")),
    "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
    "edit_file":  lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
}


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read file contents.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to file.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace exact text in file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_text": {"type": "string"},
                    "new_text": {"type": "string"},
                },
                "required": ["path", "old_text", "new_text"],
            },
        },
    },
]


SYSTEM = f"You are a coding agent at {WORKDIR}. Use tools to solve tasks."


def agent_loop(messages: list):
    """
    Error-recovering agent loop with three paths:
    1. continue after max_tokens
    2. compact after prompt-too-long
    3. back off after transient transport failure
    """
    max_output_recovery_count = 0
    while True:
        # -- Attempt the API call with connection retry --
        response = None
        for attempt in range(MAX_RECOVERY_ATTEMPTS + 1):
            try:
                # 中文注释：每轮都带 system，保证恢复策略提示持续生效。
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "system", "content": SYSTEM}] + messages,
                    tools=TOOLS,
                    max_tokens=200,
                )
                break  # success
            except Exception as e:
                error_body = str(e).lower()

                # Strategy 2: prompt_too_long -> compact and retry
                if (
                    "overlong_prompt" in error_body
                    or ("prompt" in error_body and "long" in error_body)
                    or "context_length" in error_body
                    or "maximum context" in error_body
                ):
                    print(f"[Recovery] Prompt too long. Compacting... (attempt {attempt + 1})")
                    messages[:] = auto_compact(messages)
                    continue

                # Strategy 3: connection/rate errors -> backoff
                is_transient = any(
                    token in error_body
                    for token in ("connection", "timeout", "rate", "429", "temporar", "503", "502")
                )

                if is_transient and attempt < MAX_RECOVERY_ATTEMPTS:
                    delay = backoff_delay(attempt)
                    print(f"[Recovery] API error: {e}. "
                          f"Retrying in {delay:.1f}s (attempt {attempt + 1}/{MAX_RECOVERY_ATTEMPTS})")
                    time.sleep(delay)
                    continue

                # All retries exhausted
                print(f"[Error] API call failed after {MAX_RECOVERY_ATTEMPTS} retries: {e}")
                return

        if response is None:
            print("[Error] No response received.")
            return

        
        print("\n\033[32m--- LLM Response ---\033[0m")
        print(response)
        print("\033[32m--- End Response ---\033[0m\n")
        message = response.choices[0].message
        finish_reason = response.choices[0].finish_reason

        assistant_message = {"role": "assistant", "content": message.content or ""}
        if message.tool_calls:
            # 中文注释：保留 tool_calls 元信息，便于下一轮精确关联 tool_call_id。
            assistant_message["tool_calls"] = [
                {
                    "id": tool_call.id,
                    "type": tool_call.type,
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }
                for tool_call in message.tool_calls
            ]
        messages.append(assistant_message)

        # -- Strategy 1: max_tokens recovery --
        if finish_reason == "length":
            max_output_recovery_count += 1
            print(message.content or "")
            if max_output_recovery_count <= MAX_RECOVERY_ATTEMPTS:
                print(f"[Recovery] max_tokens hit "
                      f"({max_output_recovery_count}/{MAX_RECOVERY_ATTEMPTS}). "
                      "Injecting continuation...")
                messages.append({"role": "user", "content": CONTINUATION_MESSAGE})
                continue  # retry the loop
            else:
                print(f"[Error] max_tokens recovery exhausted "
                      f"({MAX_RECOVERY_ATTEMPTS} attempts). Stopping.")
                return

        # Reset max_tokens counter on successful non-max_tokens response
        max_output_recovery_count = 0

        # -- Normal end_turn: no tool use requested --
        if finish_reason != "tool_calls" or not message.tool_calls:
            return message.content or ""

        # -- Process tool calls --
        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            try:
                # 中文注释：工具参数来自 JSON 字符串，先解析再分发执行。
                tool_input = json.loads(tool_call.function.arguments or "{}")
            except json.JSONDecodeError as exc:
                output = f"Error: invalid tool arguments: {exc}"
                print(f"  [INVALID ARGS] {tool_name}: {exc}")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(output),
                })
                continue

            handler = TOOL_HANDLERS.get(tool_name)
            try:
                output = handler(**tool_input) if handler else f"Unknown: {tool_name}"
            except Exception as e:
                output = f"Error: {e}"

            print(f"> {tool_name}: {str(output)[:200]}")
            # 中文注释：每个 tool_call 对应一条 role=tool 消息，严格对齐协议。
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(output),
            })

        # Check if we should auto-compact (proactive, not just reactive)
        if estimate_tokens(messages) > TOKEN_THRESHOLD:
            print("[Recovery] Token estimate exceeds threshold. Auto-compacting...")
            messages[:] = auto_compact(messages)


if __name__ == "__main__":
    print("[Error recovery enabled: max_tokens / prompt_too_long / connection backoff]")
    history = []
    while True:
        try:
            query = input("\033[36ms11 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        history.append({"role": "user", "content": query})
        response_text = agent_loop(history)
        if response_text:
            print(response_text)
        print()
