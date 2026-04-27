#!/usr/bin/env python3
# Harness: team mailboxes -- multiple models, coordinated through files.
"""
s15_agent_teams.py - Agent Teams
Persistent named agents with file-based JSONL inboxes. Each teammate runs
its own agent loop in a separate thread. Communication happens through
append-only inbox files.
    Subagent (s04):  spawn -> execute -> return summary -> destroyed
    Teammate (s15):  spawn -> work -> idle -> work -> ... -> shutdown
    .team/config.json                   .team/inbox/
    +----------------------------+      +------------------+
    | {"team_name": "default",   |      | alice.jsonl      |
    |  "members": [              |      | bob.jsonl        |
    |    {"name":"alice",        |      | lead.jsonl       |
    |     "role":"coder",        |      +------------------+
    |     "status":"idle"}       |
    |  ]}                        |      send_message("alice", "fix bug"):
    +----------------------------+        open("alice.jsonl", "a").write(msg)
                                        read_inbox("alice"):
    spawn_teammate("alice","coder",...)   msgs = [json.loads(l) for l in ...]
         |                                open("alice.jsonl", "w").close()
         v                                return msgs  # drain
    Thread: alice             Thread: bob
    +------------------+      +------------------+
    | agent_loop       |      | agent_loop       |
    | status: working  |      | status: idle     |
    | ... runs tools   |      | ... waits ...    |
    | status -> idle   |      |                  |
    +------------------+      +------------------+
Key idea: teammates have names, inboxes, and independent loops.
Read this file in this order:
1. MessageBus: how messages are queued and drained.
2. TeammateManager: what persistent teammate state looks like.
3. _teammate_loop / TOOL_HANDLERS: how each named teammate keeps re-entering the same tool loop.
Most common confusion:
- a teammate is not a one-shot subagent
- an inbox message is not yet a full protocol request
Teaching boundary:
this file teaches persistent named workers plus mailboxes.
Approval protocols and autonomous policies are added in later chapters.
"""
import json
import os
import subprocess
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv(override=True)

WORKDIR = Path.cwd()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is required")

client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url=os.getenv("OPENAI_BASE_URL"),
)

MODEL = os.environ["MODEL_ID"]
TEAM_DIR = WORKDIR / ".team"
INBOX_DIR = TEAM_DIR / "inbox"
SYSTEM = f"You are a team lead at {WORKDIR}. Spawn teammates and communicate via inboxes."
VALID_MSG_TYPES = {
    "message",
    "broadcast",
    "shutdown_request",
    "shutdown_response",
    "plan_approval",
    "plan_approval_response",
}


def _function_tool(name: str, description: str, properties: dict, required: list | None = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
                "additionalProperties": False,
            },
        },
    }


def _assistant_message_with_tool_calls(message) -> dict:
    tool_calls = []
    for call in message.tool_calls or []:
        tool_calls.append(
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.function.name,
                    "arguments": call.function.arguments or "{}",
                },
            }
        )

    payload = {
        "role": "assistant",
        "content": message.content or "",
    }
    if tool_calls:
        payload["tool_calls"] = tool_calls
    return payload


def _parse_tool_args(raw_args: str) -> tuple[dict | None, str | None]:
    try:
        data = json.loads(raw_args or "{}")
    except json.JSONDecodeError as exc:
        return None, f"Error: Invalid JSON arguments ({exc})"
    if not isinstance(data, dict):
        return None, "Error: Tool arguments must be a JSON object"
    return data, None


# -- MessageBus: JSONL inbox per teammate --
class MessageBus:
    def __init__(self, inbox_dir: Path):
        self.dir = inbox_dir
        self.dir.mkdir(parents=True, exist_ok=True)
    def send(self, sender: str, to: str, content: str,
             msg_type: str = "message", extra: dict = None) -> str:
        if msg_type not in VALID_MSG_TYPES:
            return f"Error: Invalid type '{msg_type}'. Valid: {VALID_MSG_TYPES}"
        msg = {
            "type": msg_type,
            "from": sender,
            "content": content,
            "timestamp": time.time(),
        }
        if extra:
            msg.update(extra)
        inbox_path = self.dir / f"{to}.jsonl"
        with open(inbox_path, "a") as f:
            f.write(json.dumps(msg) + "\n")
        return f"Sent {msg_type} to {to}"
    def read_inbox(self, name: str) -> list:
        inbox_path = self.dir / f"{name}.jsonl"
        if not inbox_path.exists():
            return []
        messages = []
        for line in inbox_path.read_text().strip().splitlines():
            if line:
                messages.append(json.loads(line))
        inbox_path.write_text("")
        return messages
    def broadcast(self, sender: str, content: str, teammates: list) -> str:
        count = 0
        for name in teammates:
            if name != sender:
                self.send(sender, name, content, "broadcast")
                count += 1
        return f"Broadcast to {count} teammates"
BUS = MessageBus(INBOX_DIR)
# -- TeammateManager: persistent named agents with config.json --
class TeammateManager:
    """Persistent teammate registry plus worker-loop launcher."""
    def __init__(self, team_dir: Path):
        self.dir = team_dir
        self.dir.mkdir(exist_ok=True)
        self.config_path = self.dir / "config.json"
        self.config = self._load_config()
        self.threads = {}
    def _load_config(self) -> dict:
        if self.config_path.exists():
            return json.loads(self.config_path.read_text())
        return {"team_name": "default", "members": []}
    def _save_config(self):
        self.config_path.write_text(json.dumps(self.config, indent=2))
    def _find_member(self, name: str) -> dict:
        for m in self.config["members"]:
            if m["name"] == name:
                return m
        return None
    def spawn(self, name: str, role: str, prompt: str) -> str:
        member = self._find_member(name)
        if member:
            if member["status"] not in ("idle", "shutdown"):
                return f"Error: '{name}' is currently {member['status']}"
            member["status"] = "working"
            member["role"] = role
        else:
            member = {"name": name, "role": role, "status": "working"}
            self.config["members"].append(member)
        self._save_config()
        thread = threading.Thread(
            target=self._teammate_loop,
            args=(name, role, prompt),
            daemon=True,
        )
        self.threads[name] = thread
        thread.start()
        return f"Spawned '{name}' (role: {role})"
    def _teammate_loop(self, name: str, role: str, prompt: str):
        sys_prompt = (
            f"You are '{name}', role: {role}, at {WORKDIR}. "
            f"Use send_message to communicate. Complete your task."
        )
        messages = [{"role": "user", "content": prompt}]
        tools = self._teammate_tools()

        for _ in range(50):
            inbox = BUS.read_inbox(name)
            for msg in inbox:
                messages.append({"role": "user", "content": json.dumps(msg)})

            try:
                # 关键请求点：统一走 OpenAI chat-completions 形态。
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "system", "content": sys_prompt}, *messages],
                    tools=tools,
                    max_tokens=8000,
                )
            except Exception:
                break

            assistant = response.choices[0].message
            messages.append(_assistant_message_with_tool_calls(assistant))
            if not assistant.tool_calls:
                break

            for call in assistant.tool_calls:
                # 关键容错点：工具参数 JSON 解析失败时返回结构化错误。
                parsed_args, parse_error = _parse_tool_args(call.function.arguments)
                if parse_error:
                    output = parse_error
                else:
                    output = self._exec(name, call.function.name, parsed_args)
                print(f"  [{name}] {call.function.name}: {str(output)[:120]}")

                # 关键回注点：把工具执行结果以 role=tool 注入会话。
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": str(output),
                    }
                )

        member = self._find_member(name)
        if member and member["status"] != "shutdown":
            member["status"] = "idle"
            self._save_config()
    def _exec(self, sender: str, tool_name: str, args: dict) -> str:
        # these base tools are unchanged from s02
        if tool_name == "bash":
            return _run_bash(args["command"])
        if tool_name == "read_file":
            return _run_read(args["path"])
        if tool_name == "write_file":
            return _run_write(args["path"], args["content"])
        if tool_name == "edit_file":
            return _run_edit(args["path"], args["old_text"], args["new_text"])
        if tool_name == "send_message":
            return BUS.send(sender, args["to"], args["content"], args.get("msg_type", "message"))
        if tool_name == "read_inbox":
            return json.dumps(BUS.read_inbox(sender), indent=2)
        return f"Unknown tool: {tool_name}"
    def _teammate_tools(self) -> list:
        # these base tools are unchanged from s02
        return [
            _function_tool(
                "bash",
                "Run a shell command.",
                {"command": {"type": "string"}},
                ["command"],
            ),
            _function_tool(
                "read_file",
                "Read file contents.",
                {"path": {"type": "string"}},
                ["path"],
            ),
            _function_tool(
                "write_file",
                "Write content to file.",
                {"path": {"type": "string"}, "content": {"type": "string"}},
                ["path", "content"],
            ),
            _function_tool(
                "edit_file",
                "Replace exact text in file.",
                {
                    "path": {"type": "string"},
                    "old_text": {"type": "string"},
                    "new_text": {"type": "string"},
                },
                ["path", "old_text", "new_text"],
            ),
            _function_tool(
                "send_message",
                "Send message to a teammate.",
                {
                    "to": {"type": "string"},
                    "content": {"type": "string"},
                    "msg_type": {"type": "string", "enum": list(VALID_MSG_TYPES)},
                },
                ["to", "content"],
            ),
            _function_tool(
                "read_inbox",
                "Read and drain your inbox.",
                {},
            ),
        ]
    def list_all(self) -> str:
        if not self.config["members"]:
            return "No teammates."
        lines = [f"Team: {self.config['team_name']}"]
        for m in self.config["members"]:
            lines.append(f"  {m['name']} ({m['role']}): {m['status']}")
        return "\n".join(lines)
    def member_names(self) -> list:
        return [m["name"] for m in self.config["members"]]
TEAM = TeammateManager(TEAM_DIR)
# -- Base tool implementations (these base tools are unchanged from s02) --
def _safe_path(p: str) -> Path:
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path
def _run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot"]
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"
    try:
        r = subprocess.run(
            command, shell=True, cwd=WORKDIR,
            capture_output=True, text=True, timeout=120,
        )
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"
def _run_read(path: str, limit: int = None) -> str:
    try:
        lines = _safe_path(path).read_text().splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more)"]
        return "\n".join(lines)[:50000]
    except Exception as e:
        return f"Error: {e}"
def _run_write(path: str, content: str) -> str:
    try:
        fp = _safe_path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content)
        return f"Wrote {len(content)} bytes"
    except Exception as e:
        return f"Error: {e}"
def _run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        fp = _safe_path(path)
        c = fp.read_text()
        if old_text not in c:
            return f"Error: Text not found in {path}"
        fp.write_text(c.replace(old_text, new_text, 1))
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"
# -- Lead tool dispatch (9 tools) --
TOOL_HANDLERS = {
    "bash":            lambda **kw: _run_bash(kw["command"]),
    "read_file":       lambda **kw: _run_read(kw["path"], kw.get("limit")),
    "write_file":      lambda **kw: _run_write(kw["path"], kw["content"]),
    "edit_file":       lambda **kw: _run_edit(kw["path"], kw["old_text"], kw["new_text"]),
    "spawn_teammate":  lambda **kw: TEAM.spawn(kw["name"], kw["role"], kw["prompt"]),
    "list_teammates":  lambda **kw: TEAM.list_all(),
    "send_message":    lambda **kw: BUS.send("lead", kw["to"], kw["content"], kw.get("msg_type", "message")),
    "read_inbox":      lambda **kw: json.dumps(BUS.read_inbox("lead"), indent=2),
    "broadcast":       lambda **kw: BUS.broadcast("lead", kw["content"], TEAM.member_names()),
}
# these base tools are unchanged from s02
TOOLS = [
    _function_tool(
        "bash",
        "Run a shell command.",
        {"command": {"type": "string"}},
        ["command"],
    ),
    _function_tool(
        "read_file",
        "Read file contents.",
        {"path": {"type": "string"}, "limit": {"type": "integer"}},
        ["path"],
    ),
    _function_tool(
        "write_file",
        "Write content to file.",
        {"path": {"type": "string"}, "content": {"type": "string"}},
        ["path", "content"],
    ),
    _function_tool(
        "edit_file",
        "Replace exact text in file.",
        {
            "path": {"type": "string"},
            "old_text": {"type": "string"},
            "new_text": {"type": "string"},
        },
        ["path", "old_text", "new_text"],
    ),
    _function_tool(
        "spawn_teammate",
        "Spawn a persistent teammate that runs in its own thread.",
        {
            "name": {"type": "string"},
            "role": {"type": "string"},
            "prompt": {"type": "string"},
        },
        ["name", "role", "prompt"],
    ),
    _function_tool(
        "list_teammates",
        "List all teammates with name, role, status.",
        {},
    ),
    _function_tool(
        "send_message",
        "Send a message to a teammate's inbox.",
        {
            "to": {"type": "string"},
            "content": {"type": "string"},
            "msg_type": {"type": "string", "enum": list(VALID_MSG_TYPES)},
        },
        ["to", "content"],
    ),
    _function_tool(
        "read_inbox",
        "Read and drain the lead's inbox.",
        {},
    ),
    _function_tool(
        "broadcast",
        "Send a message to all teammates.",
        {"content": {"type": "string"}},
        ["content"],
    ),
]


def agent_loop(messages: list):
    while True:
        inbox = BUS.read_inbox("lead")
        if inbox:
            messages.append({
                "role": "user",
                "content": f"<inbox>{json.dumps(inbox, indent=2)}</inbox>",
            })

        # 关键请求点：主循环改为 OpenAI chat-completions。
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": SYSTEM}, *messages],
            tools=TOOLS,
            max_tokens=8000,
        )

        assistant = response.choices[0].message
        messages.append(_assistant_message_with_tool_calls(assistant))
        if not assistant.tool_calls:
            return

        for call in assistant.tool_calls:
            # 关键容错点：工具参数来自模型文本，先做 JSON 解析校验。
            parsed_args, parse_error = _parse_tool_args(call.function.arguments)
            if parse_error:
                output = parse_error
            else:
                handler = TOOL_HANDLERS.get(call.function.name)
                try:
                    output = handler(**parsed_args) if handler else f"Unknown tool: {call.function.name}"
                except Exception as e:
                    output = f"Error: {e}"

            print(f"> {call.function.name}:")
            print(str(output)[:200])

            # 关键回注点：工具结果注入 role=tool，并关联 tool_call_id。
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": str(output),
                }
            )


if __name__ == "__main__":
    history = []
    while True:
        try:
            query = input("\033[36ms15 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        if query.strip() == "/team":
            print(TEAM.list_all())
            continue
        if query.strip() == "/inbox":
            print(json.dumps(BUS.read_inbox("lead"), indent=2))
            continue
        history.append({"role": "user", "content": query})
        agent_loop(history)

        response_content = history[-1].get("content", "")
        if isinstance(response_content, str) and response_content.strip():
            print(response_content)
        print()