#!/usr/bin/env python3
# Harness: all mechanisms combined -- the complete cockpit for the model.
"""
miniClaudeCode.py - Full Reference Agent

Capstone implementation combining core mechanisms plus later integrations.
Task system is aligned to s12, background tasks to s13, and team to s15.
NOT a teaching session -- this is the "put it all together" reference.

    +------------------------------------------------------------------+
    |                        FULL AGENT                                 |
    |                                                                   |
    |  System prompt (s05 skills, task-first + optional todo nag)      |
    |                                                                   |
    |  Before each LLM call:                                            |
    |  +--------------------+  +------------------+  +--------------+  |
    |  | Microcompact (s06) |  | Drain bg (s13)   |  | Check inbox  |  |
    |  | Auto-compact (s06) |  | notifications    |  | (s15)        |  |
    |  +--------------------+  +------------------+  +--------------+  |
    |                                                                   |
    |  Tool dispatch (s02 pattern):                                     |
    |  +--------+----------+----------+---------+-----------+          |
    |  | bash   | read     | write    | edit    | TodoWrite |          |
    |  | task   | load_sk  | compress | bg_run  | bg_check  |          |
    |  | t_crt  | t_get    | t_upd    | t_list  | spawn_tm  |          |
    |  | list_tm| send_msg | rd_inbox | bcast   | shutdown  |          |
    |  | plan   | idle     | claim    |         |           |          |
    |  +--------+----------+----------+---------+-----------+          |
    |                                                                   |
    |  Subagent (s04):  spawn -> work -> return summary                 |
    |  Teammate (s15):  spawn -> work -> idle -> auto-claim (s11)      |
    |  Shutdown (s10):  request_id handshake                            |
    |  Plan gate (s10): submit -> approve/reject                        |
    +------------------------------------------------------------------+

    REPL commands: /compact /tasks /team /inbox
"""

import json
import os
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path
from queue import Queue

from dotenv import load_dotenv
from openai import OpenAI
import yaml

load_dotenv(override=True)

WORKDIR = Path.cwd()
client = OpenAI(
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=os.getenv("OPENAI_BASE_URL"),
)
MODEL = os.environ["MODEL_ID"]

TEAM_DIR = WORKDIR / ".team"
INBOX_DIR = TEAM_DIR / "inbox"
TASKS_DIR = WORKDIR / ".tasks"
SKILLS_DIR = WORKDIR / "skills"
TRANSCRIPT_DIR = WORKDIR / ".transcripts"
MESSAGES_DIR = WORKDIR / ".messages"
TOKEN_THRESHOLD = 100000
POLL_INTERVAL = 5
IDLE_TIMEOUT = 60

VALID_MSG_TYPES = {"message", "broadcast", "shutdown_request",
                   "shutdown_response", "plan_approval_response"}


# === SECTION: base_tools ===
def make_tool(name: str, description: str, parameters: dict) -> dict:
    """把工具统一生成成 OpenAI function tools 结构，避免每个工具重复写样板"""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
        },
    }


def safe_path(p: str) -> Path:
    """防止工具被用来访问工作区外的文件，传的都是相对路径"""
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path

def run_bash(command: str) -> str:
    """执行 bash 命令，防止危险操作"""
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(d in command for d in dangerous):
        return f"Error: Dangerous command blocked. [{command}]"
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
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"

def run_edit(path: str, old_text: str, new_text: str) -> str:
    """在文件中替换第一处出现的文本，适合小范围修改"""
    try:
        fp = safe_path(path)
        c = fp.read_text()
        if old_text not in c:
            return f"Error: Text not found in {path}"
        fp.write_text(c.replace(old_text, new_text, 1))
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"


# === SECTION: todos (s03) ===
class TodoManager:
    def __init__(self):
        self.items = []

    def update(self, items: list) -> str:
        """
        接收待办事项列表，验证并存储。每项包含 content, status, activeForm
        最多支持 20 条代办事项，且只能有一条 in_progress
        """
        validated, ip = [], 0
        for i, item in enumerate(items):
            content = str(item.get("content", "")).strip()
            status = str(item.get("status", "pending")).lower()
            af = str(item.get("activeForm", "")).strip()
            if not content: raise ValueError(f"Item {i}: content required")
            if status not in ("pending", "in_progress", "completed"):
                raise ValueError(f"Item {i}: invalid status '{status}'")
            if not af: raise ValueError(f"Item {i}: activeForm required")
            if status == "in_progress": ip += 1
            validated.append({"content": content, "status": status, "activeForm": af})
        if len(validated) > 20: raise ValueError("Max 20 todos")
        if ip > 1: raise ValueError("Only one in_progress allowed")
        self.items = validated
        return self._render()

    def _render(self) -> str:
        if not self.items: return "No todos."
        lines = []
        for item in self.items:
            m = {"completed": "[x]", "in_progress": "[>]", "pending": "[ ]"}.get(item["status"], "[?]")
            suffix = f" <- {item['activeForm']}" if item["status"] == "in_progress" else ""
            lines.append(f"{m} {item['content']}{suffix}")
        done = sum(1 for t in self.items if t["status"] == "completed")
        lines.append(f"\n({done}/{len(self.items)} completed)")
        return "\n".join(lines)

    def has_open_items(self) -> bool:
        """检查是否有未完成的事项，决定是否继续循环"""
        return any(item.get("status") != "completed" for item in self.items)


# === SECTION: subagent (s04) ===
def run_subagent(prompt: str, agent_type: str = "Explore") -> str:
    def _persist_subagent_messages(all_messages: list, final_text: str) -> None:
        """sub-agent 结束后，把完整消息轨迹落盘到 .messages/*.json。"""
        try:
            MESSAGES_DIR.mkdir(exist_ok=True)
            payload = {
                "saved_at": time.time(),
                "agent_type": agent_type,
                "prompt": prompt,
                "final_text": final_text,
                "messages": all_messages,
            }
            filename = f"subagent_{int(time.time())}_{uuid.uuid4().hex[:8]}.json"
            (MESSAGES_DIR / filename).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2)
            )
        except Exception:
            # 持久化失败不影响主流程，避免因为日志写入导致任务失败。
            pass

    # 子智能体只支持调用部分工具，且不允许写文件（以免失控）。Explore 型只能读文件，Work 型可以读写。
    sub_tools = [
        make_tool(
            "bash",
            "Run command.",
            {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        ),
        make_tool(
            "read_file",
            "Read file.",
            {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        ),
    ]

    if agent_type != "Explore":
        sub_tools += [
            make_tool(
                "write_file",
                "Write file.",
                {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            ),
            make_tool(
                "edit_file",
                "Edit file.",
                {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "old_text": {"type": "string"},
                        "new_text": {"type": "string"},
                    },
                    "required": ["path", "old_text", "new_text"],
                },
            ),
        ]

    sub_handlers = {
        "bash": lambda **kw: run_bash(kw["command"]),
        "read_file": lambda **kw: run_read(kw["path"]),
        "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
        "edit_file": lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
    }

    sub_msgs = [{"role": "user", "content": prompt}]

    final_text = ""
    # 子智能体循环，最多 30 轮工具调用。每轮调用后都把工具结果回注到消息中，直到模型不再调用工具或达到轮数上限。
    for _ in range(30):
        # OpenAI 兼容请求：system 置于首条消息，tools 使用 function schema。
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are a focused subagent."},
                *sub_msgs,
            ],
            tools=sub_tools,
            max_tokens=8000,
        )

        msg = resp.choices[0].message
        final_text = msg.content or ""

        assistant_msg = {"role": "assistant", "content": final_text}
        if msg.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments or "{}",
                    },
                }
                for tc in msg.tool_calls
            ]
        sub_msgs.append(assistant_msg)

        if not msg.tool_calls:
            _persist_subagent_messages(sub_msgs, final_text)
            return final_text or "(no summary)"

        for tool_call in msg.tool_calls:
            name = tool_call.function.name
            handler = sub_handlers.get(name)

            # 工具参数来自模型文本，需要 JSON 解析和异常兜底。
            try:
                parsed_args = json.loads(tool_call.function.arguments or "{}")
                if not isinstance(parsed_args, dict):
                    raise ValueError("Arguments must be a JSON object")
            except Exception as e:
                output = f"Error: Invalid tool arguments: {e}"
            else:
                try:
                    output = handler(**parsed_args) if handler else "Unknown tool"
                except Exception as e:
                    output = f"Error: {e}"

            sub_msgs.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(output)[:50000],
                }
            )

    _persist_subagent_messages(sub_msgs, final_text)
    return final_text or "(subagent failed)"


# === SECTION: skills (s05) ===
class SkillLoader:
    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self.skills = {}
        self._load_all()

    def _load_all(self):
        if not self.skills_dir.exists():
            return
        for f in sorted(self.skills_dir.rglob("SKILL.md")):
            text = f.read_text()
            meta, body = self._parse_frontmatter(text)
            name = meta.get("name", f.parent.name)
            self.skills[name] = {"meta": meta, "body": body}

    def _parse_frontmatter(self, text: str) -> tuple:
        """用 YAML 解析 --- frontmatter ---，失败时回退为纯正文。"""
        match = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
        if not match:
            return {}, text
        try:
            meta = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            meta = {}
        return meta, match.group(2).strip()

    def descriptions(self) -> str:
        if not self.skills: return "(no skills)"
        return "\n".join(f"  - {n}: {s['meta'].get('description', '-')}" for n, s in self.skills.items())

    def load(self, name: str) -> str:
        s = self.skills.get(name)
        if not s: return f"Error: Unknown skill '{name}'. Available: {', '.join(self.skills.keys())}"
        return f"<skill name=\"{name}\">\n{s['body']}\n</skill>"


# === SECTION: compression (s06) ===
def estimate_tokens(messages: list) -> int:
    return len(json.dumps(messages, default=str)) // 4

def microcompact(messages: list):
    """轻量级压缩，就地清除旧的、冗长的工具输出，每次 Agent Loop 前调用"""
    indices = []
    for i, msg in enumerate(messages):
        if msg.get("role") == "tool" and isinstance(msg.get("content"), str):
            indices.append(i)

    if len(indices) <= 3:
        return

    for idx in indices[:-3]:
        if len(messages[idx]["content"]) > 100:
            messages[idx]["content"] = "[cleared]"

def auto_compact(messages: list) -> list:
    """自动压缩，彻底删除旧消息并保留摘要。超过 TOKEN_THRESHOLD 时调用，返回压缩后的消息列表"""
    TRANSCRIPT_DIR.mkdir(exist_ok=True)
    path = TRANSCRIPT_DIR / f"transcript_{int(time.time())}.jsonl"
    with open(path, "w") as f:
        for msg in messages:
            f.write(json.dumps(msg, default=str) + "\n")
    conv_text = json.dumps(messages, default=str)[-80000:]
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "Summarize for continuity."},
            {"role": "user", "content": conv_text},
        ],
        max_tokens=2000,
    )
    summary = resp.choices[0].message.content or "(no summary)"
    return [
        {"role": "user", "content": f"[Compressed. Transcript: {path}]\n{summary}"},
    ]


# === SECTION: tasks_system (s12) ===
class TaskManager:
    def __init__(self):
        TASKS_DIR.mkdir(exist_ok=True)

    def _next_id(self) -> int:
        ids = [int(f.stem.split("_")[1]) for f in TASKS_DIR.glob("task_*.json")]
        return max(ids, default=0) + 1

    def _load(self, tid: int) -> dict:
        p = TASKS_DIR / f"task_{tid}.json"
        if not p.exists(): raise ValueError(f"Task {tid} not found")
        return json.loads(p.read_text())

    def _save(self, task: dict):
        (TASKS_DIR / f"task_{task['id']}.json").write_text(json.dumps(task, indent=2))

    def create(self, subject: str, description: str = "") -> str:
        task = {"id": self._next_id(), "subject": subject, "description": description,
                "status": "pending", "owner": None, "blockedBy": []}
        self._save(task)
        return json.dumps(task, indent=2)

    def get(self, tid: int) -> str:
        return json.dumps(self._load(tid), indent=2)

    def update(self, tid: int, status: str = None,
               add_blocked_by: list = None, remove_blocked_by: list = None) -> str:
        task = self._load(tid)
        if status:
            task["status"] = status
            if status == "completed":
                for f in TASKS_DIR.glob("task_*.json"):
                    t = json.loads(f.read_text())
                    if tid in t.get("blockedBy", []):
                        t["blockedBy"].remove(tid)
                        self._save(t)
            if status == "deleted":
                (TASKS_DIR / f"task_{tid}.json").unlink(missing_ok=True)
                return f"Task {tid} deleted"
        if add_blocked_by:
            task["blockedBy"] = list(set(task["blockedBy"] + add_blocked_by))
        if remove_blocked_by:
            task["blockedBy"] = [x for x in task["blockedBy"] if x not in remove_blocked_by]
        self._save(task)
        return json.dumps(task, indent=2)

    def list_all(self) -> str:
        tasks = [json.loads(f.read_text()) for f in sorted(TASKS_DIR.glob("task_*.json"))]
        if not tasks: return "No tasks."
        lines = []
        for t in tasks:
            m = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]"}.get(t["status"], "[?]")
            owner = f" @{t['owner']}" if t.get("owner") else ""
            blocked = f" (blocked by: {t['blockedBy']})" if t.get("blockedBy") else ""
            lines.append(f"{m} #{t['id']}: {t['subject']}{owner}{blocked}")
        return "\n".join(lines)

    def claim(self, tid: int, owner: str) -> str:
        task = self._load(tid)
        task["owner"] = owner
        task["status"] = "in_progress"
        self._save(task)
        return f"Claimed task #{tid} for {owner}"


# === SECTION: background_tasks (s13) ===
class BackgroundManager:
    def __init__(self):
        self.tasks = {}
        self.notifications = Queue()

    def run(self, command: str, timeout: int = 120) -> str:
        tid = str(uuid.uuid4())[:8]
        self.tasks[tid] = {"status": "running", "command": command, "result": None}
        threading.Thread(target=self._exec, args=(tid, command, timeout), daemon=True).start()
        return f"Background task {tid} started: {command[:80]}"

    def _exec(self, tid: str, command: str, timeout: int):
        try:
            r = subprocess.run(command, shell=True, cwd=WORKDIR,
                               capture_output=True, text=True, timeout=timeout)
            output = (r.stdout + r.stderr).strip()[:50000]
            self.tasks[tid].update({"status": "completed", "result": output or "(no output)"})
        except Exception as e:
            self.tasks[tid].update({"status": "error", "result": str(e)})
        self.notifications.put({"task_id": tid, "status": self.tasks[tid]["status"],
                                "result": self.tasks[tid]["result"][:500]})

    def check(self, tid: str = None) -> str:
        if tid:
            t = self.tasks.get(tid)
            return f"[{t['status']}] {t.get('result') or '(running)'}" if t else f"Unknown: {tid}"
        return "\n".join(f"{k}: [{v['status']}] {v['command'][:60]}" for k, v in self.tasks.items()) or "No bg tasks."

    def drain(self) -> list:
        notifs = []
        while not self.notifications.empty():
            notifs.append(self.notifications.get_nowait())
        return notifs


# === SECTION: messaging (s09) ===
class MessageBus:
    def __init__(self):
        INBOX_DIR.mkdir(parents=True, exist_ok=True)

    def send(self, sender: str, to: str, content: str,
             msg_type: str = "message", extra: dict = None) -> str:
        msg = {"type": msg_type, "from": sender, "content": content,
               "timestamp": time.time()}
        if extra: msg.update(extra)
        with open(INBOX_DIR / f"{to}.jsonl", "a") as f:
            f.write(json.dumps(msg) + "\n")
        return f"Sent {msg_type} to {to}"

    def read_inbox(self, name: str) -> list:
        path = INBOX_DIR / f"{name}.jsonl"
        if not path.exists(): return []
        msgs = [json.loads(l) for l in path.read_text().strip().splitlines() if l]
        path.write_text("")
        return msgs

    def broadcast(self, sender: str, content: str, names: list) -> str:
        count = 0
        for n in names:
            if n != sender:
                self.send(sender, n, content, "broadcast")
                count += 1
        return f"Broadcast to {count} teammates"


# === SECTION: shutdown + plan tracking (s10) ===
shutdown_requests = {}
plan_requests = {}


# === SECTION: team (s15) ===
class TeammateManager:
    def __init__(self, bus: MessageBus, task_mgr: TaskManager):
        TEAM_DIR.mkdir(exist_ok=True)
        self.bus = bus
        self.task_mgr = task_mgr
        self.config_path = TEAM_DIR / "config.json"
        self.config = self._load()
        self.threads = {}

    def _load(self) -> dict:
        if self.config_path.exists():
            return json.loads(self.config_path.read_text())
        return {"team_name": "default", "members": []}

    def _save(self):
        self.config_path.write_text(json.dumps(self.config, indent=2))

    def _find(self, name: str) -> dict:
        for m in self.config["members"]:
            if m["name"] == name: return m
        return None

    def spawn(self, name: str, role: str, prompt: str) -> str:
        member = self._find(name)
        if member:
            if member["status"] not in ("idle", "shutdown"):
                return f"Error: '{name}' is currently {member['status']}"
            member["status"] = "working"
            member["role"] = role
        else:
            member = {"name": name, "role": role, "status": "working"}
            self.config["members"].append(member)
        self._save()
        threading.Thread(target=self._loop, args=(name, role, prompt), daemon=True).start()
        return f"Spawned '{name}' (role: {role})"

    def _set_status(self, name: str, status: str):
        member = self._find(name)
        if member:
            member["status"] = status
            self._save()

    def _loop(self, name: str, role: str, prompt: str):
        team_name = self.config["team_name"]
        sys_prompt = (f"You are '{name}', role: {role}, team: {team_name}, at {WORKDIR}. "
                      f"Use idle when done with current work. You may auto-claim tasks.")
        messages = [{"role": "user", "content": prompt}]
        tools = [
            make_tool(
                "bash",
                "Run command.",
                {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
            ),
            make_tool(
                "read_file",
                "Read file.",
                {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            ),
            make_tool(
                "write_file",
                "Write file.",
                {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            ),
            make_tool(
                "edit_file",
                "Edit file.",
                {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "old_text": {"type": "string"},
                        "new_text": {"type": "string"},
                    },
                    "required": ["path", "old_text", "new_text"],
                },
            ),
            make_tool(
                "send_message",
                "Send message.",
                {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["to", "content"],
                },
            ),
            make_tool("idle", "Signal no more work.", {"type": "object", "properties": {}}),
            make_tool(
                "claim_task",
                "Claim task by ID.",
                {
                    "type": "object",
                    "properties": {"task_id": {"type": "integer"}},
                    "required": ["task_id"],
                },
            ),
        ]
        while True:
            # -- WORK PHASE --
            for _ in range(50):
                inbox = self.bus.read_inbox(name)
                for msg in inbox:
                    if msg.get("type") == "shutdown_request":
                        self._set_status(name, "shutdown")
                        return
                    messages.append({"role": "user", "content": json.dumps(msg)})
                try:
                    # 队友循环也统一走 OpenAI chat-completions。
                    response = client.chat.completions.create(
                        model=MODEL,
                        messages=[{"role": "system", "content": sys_prompt}, *messages],
                        tools=tools,
                        max_tokens=8000,
                    )
                except Exception:
                    self._set_status(name, "shutdown")
                    return

                msg = response.choices[0].message
                assistant_msg = {
                    "role": "assistant",
                    "content": msg.content or "",
                }
                if msg.tool_calls:
                    assistant_msg["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments or "{}",
                            },
                        }
                        for tc in msg.tool_calls
                    ]
                messages.append(assistant_msg)

                if not msg.tool_calls:
                    break

                idle_requested = False

                for tool_call in msg.tool_calls:
                    name_call = tool_call.function.name

                    # 先解析工具参数，避免模型输出非 JSON 时直接崩溃。
                    try:
                        parsed_args = json.loads(tool_call.function.arguments or "{}")
                        if not isinstance(parsed_args, dict):
                            raise ValueError("Arguments must be a JSON object")
                    except Exception as e:
                        output = f"Error: Invalid tool arguments: {e}"
                    else:
                        if name_call == "idle":
                            idle_requested = True
                            output = "Entering idle phase."
                        elif name_call == "claim_task":
                            output = self.task_mgr.claim(parsed_args["task_id"], name)
                        elif name_call == "send_message":
                            output = self.bus.send(name, parsed_args["to"], parsed_args["content"])
                        else:
                            dispatch = {"bash": lambda **kw: run_bash(kw["command"]),
                                        "read_file": lambda **kw: run_read(kw["path"]),
                                        "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
                                        "edit_file": lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"])}
                            output = dispatch.get(name_call, lambda **kw: "Unknown")(**parsed_args)

                    print(f"  [{name}] {name_call}: {str(output)[:120]}")

                    # 回注 role=tool，确保模型可以关联到对应的 tool_call。
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": str(output),
                        }
                    )

                if idle_requested:
                    break
            # -- IDLE PHASE: poll for messages and unclaimed tasks --
            self._set_status(name, "idle")
            resume = False
            for _ in range(IDLE_TIMEOUT // max(POLL_INTERVAL, 1)):
                time.sleep(POLL_INTERVAL)
                inbox = self.bus.read_inbox(name)
                if inbox:
                    for msg in inbox:
                        if msg.get("type") == "shutdown_request":
                            self._set_status(name, "shutdown")
                            return
                        messages.append({"role": "user", "content": json.dumps(msg)})
                    resume = True
                    break
                unclaimed = []
                for f in sorted(TASKS_DIR.glob("task_*.json")):
                    t = json.loads(f.read_text())
                    if t.get("status") == "pending" and not t.get("owner") and not t.get("blockedBy"):
                        unclaimed.append(t)
                if unclaimed:
                    task = unclaimed[0]
                    self.task_mgr.claim(task["id"], name)
                    # Identity re-injection for compressed contexts
                    if len(messages) <= 3:
                        messages.insert(0, {"role": "user", "content":
                            f"<identity>You are '{name}', role: {role}, team: {team_name}.</identity>"})
                        messages.insert(1, {"role": "assistant", "content": f"I am {name}. Continuing."})
                    messages.append({"role": "user", "content":
                        f"<auto-claimed>Task #{task['id']}: {task['subject']}\n{task.get('description', '')}</auto-claimed>"})
                    messages.append({"role": "assistant", "content": f"Claimed task #{task['id']}. Working on it."})
                    resume = True
                    break
            if not resume:
                self._set_status(name, "shutdown")
                return
            self._set_status(name, "working")

    def list_all(self) -> str:
        if not self.config["members"]: return "No teammates."
        lines = [f"Team: {self.config['team_name']}"]
        for m in self.config["members"]:
            lines.append(f"  {m['name']} ({m['role']}): {m['status']}")
        return "\n".join(lines)

    def member_names(self) -> list:
        return [m["name"] for m in self.config["members"]]


# === SECTION: global_instances ===
TODO = TodoManager()
SKILLS = SkillLoader(SKILLS_DIR)
TASK_MGR = TaskManager()
BG = BackgroundManager()
BUS = MessageBus()
TEAM = TeammateManager(BUS, TASK_MGR)

# === SECTION: system_prompt ===
SYSTEM = f"""You are a coding agent at {WORKDIR}. Use tools to solve tasks.
Prefer task_create/task_update/task_list for multi-step work. Use TodoWrite for short checklists.
Use task for subagent delegation. Use load_skill for specialized knowledge.
Skills: {SKILLS.descriptions()}"""


# === SECTION: shutdown_protocol (s10) ===
def handle_shutdown_request(teammate: str) -> str:
    req_id = str(uuid.uuid4())[:8]
    shutdown_requests[req_id] = {"target": teammate, "status": "pending"}
    BUS.send("lead", teammate, "Please shut down.", "shutdown_request", {"request_id": req_id})
    return f"Shutdown request {req_id} sent to '{teammate}'"

# === SECTION: plan_approval (s10) ===
def handle_plan_review(request_id: str, approve: bool, feedback: str = "") -> str:
    req = plan_requests.get(request_id)
    if not req: return f"Error: Unknown plan request_id '{request_id}'"
    req["status"] = "approved" if approve else "rejected"
    BUS.send("lead", req["from"], feedback, "plan_approval_response",
             {"request_id": request_id, "approve": approve, "feedback": feedback})
    return f"Plan {req['status']} for '{req['from']}'"


# === SECTION: tool_dispatch (s02) ===
TOOL_HANDLERS = {
    "bash":             lambda **kw: run_bash(kw["command"]),
    "read_file":        lambda **kw: run_read(kw["path"], kw.get("limit")),
    "write_file":       lambda **kw: run_write(kw["path"], kw["content"]),
    "edit_file":        lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
    "TodoWrite":        lambda **kw: TODO.update(kw["items"]),
    "task":             lambda **kw: run_subagent(kw["prompt"], kw.get("agent_type", "Explore")),
    "load_skill":       lambda **kw: SKILLS.load(kw["name"]),
    "compress":         lambda **kw: "Compressing...",
    "background_run":   lambda **kw: BG.run(kw["command"], kw.get("timeout", 120)),
    "check_background": lambda **kw: BG.check(kw.get("task_id")),
    "task_create":      lambda **kw: TASK_MGR.create(kw["subject"], kw.get("description", "")),
    "task_get":         lambda **kw: TASK_MGR.get(kw["task_id"]),
    "task_update":      lambda **kw: TASK_MGR.update(kw["task_id"], kw.get("status"), kw.get("add_blocked_by"), kw.get("remove_blocked_by")),
    "task_list":        lambda **kw: TASK_MGR.list_all(),
    "spawn_teammate":   lambda **kw: TEAM.spawn(kw["name"], kw["role"], kw["prompt"]),
    "list_teammates":   lambda **kw: TEAM.list_all(),
    "send_message":     lambda **kw: BUS.send("lead", kw["to"], kw["content"], kw.get("msg_type", "message")),
    "read_inbox":       lambda **kw: json.dumps(BUS.read_inbox("lead"), indent=2),
    "broadcast":        lambda **kw: BUS.broadcast("lead", kw["content"], TEAM.member_names()),
    "shutdown_request": lambda **kw: handle_shutdown_request(kw["teammate"]),
    "plan_approval":    lambda **kw: handle_plan_review(kw["request_id"], kw["approve"], kw.get("feedback", "")),
    "idle":             lambda **kw: "Lead does not idle.",
    "claim_task":       lambda **kw: TASK_MGR.claim(kw["task_id"], "lead"),
}

TOOLS = [
    make_tool(
        "bash",
        "Run a shell command.",
        {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    ),
    make_tool(
        "read_file",
        "Read file contents.",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["path"],
        },
    ),
    make_tool(
        "write_file",
        "Write content to file.",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    ),
    make_tool(
        "edit_file",
        "Replace exact text in file.",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
            },
            "required": ["path", "old_text", "new_text"],
        },
    ),
    make_tool(
        "TodoWrite",
        "Update task tracking list.",
        {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string"},
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed"],
                            },
                            "activeForm": {"type": "string"},
                        },
                        "required": ["content", "status", "activeForm"],
                    },
                }
            },
            "required": ["items"],
        },
    ),
    make_tool(
        "task",
        "Spawn a subagent for isolated exploration or work.",
        {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "agent_type": {
                    "type": "string",
                    "enum": ["Explore", "general-purpose"],
                },
            },
            "required": ["prompt"],
        },
    ),
    make_tool(
        "load_skill",
        "Load specialized knowledge by name.",
        {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    ),
    make_tool("compress", "Manually compress conversation context.", {"type": "object", "properties": {}}),
    make_tool(
        "background_run",
        "Run command in background thread.",
        {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout": {"type": "integer"},
            },
            "required": ["command"],
        },
    ),
    make_tool(
        "check_background",
        "Check background task status.",
        {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
        },
    ),
    make_tool(
        "task_create",
        "Create a persistent file task.",
        {
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["subject"],
        },
    ),
    make_tool(
        "task_get",
        "Get task details by ID.",
        {
            "type": "object",
            "properties": {"task_id": {"type": "integer"}},
            "required": ["task_id"],
        },
    ),
    make_tool(
        "task_update",
        "Update task status or dependencies.",
        {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "completed", "deleted"],
                },
                "add_blocked_by": {"type": "array", "items": {"type": "integer"}},
                "remove_blocked_by": {"type": "array", "items": {"type": "integer"}},
            },
            "required": ["task_id"],
        },
    ),
    make_tool("task_list", "List all tasks.", {"type": "object", "properties": {}}),
    make_tool(
        "spawn_teammate",
        "Spawn a persistent autonomous teammate.",
        {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "role": {"type": "string"},
                "prompt": {"type": "string"},
            },
            "required": ["name", "role", "prompt"],
        },
    ),
    make_tool("list_teammates", "List all teammates.", {"type": "object", "properties": {}}),
    make_tool(
        "send_message",
        "Send a message to a teammate.",
        {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "content": {"type": "string"},
                "msg_type": {"type": "string", "enum": list(VALID_MSG_TYPES)},
            },
            "required": ["to", "content"],
        },
    ),
    make_tool("read_inbox", "Read and drain the lead's inbox.", {"type": "object", "properties": {}}),
    make_tool(
        "broadcast",
        "Send message to all teammates.",
        {
            "type": "object",
            "properties": {"content": {"type": "string"}},
            "required": ["content"],
        },
    ),
    make_tool(
        "shutdown_request",
        "Request a teammate to shut down.",
        {
            "type": "object",
            "properties": {"teammate": {"type": "string"}},
            "required": ["teammate"],
        },
    ),
    make_tool(
        "plan_approval",
        "Approve or reject a teammate's plan.",
        {
            "type": "object",
            "properties": {
                "request_id": {"type": "string"},
                "approve": {"type": "boolean"},
                "feedback": {"type": "string"},
            },
            "required": ["request_id", "approve"],
        },
    ),
    make_tool("idle", "Enter idle state.", {"type": "object", "properties": {}}),
    make_tool(
        "claim_task",
        "Claim a task from the board.",
        {
            "type": "object",
            "properties": {"task_id": {"type": "integer"}},
            "required": ["task_id"],
        },
    ),
]


# === SECTION: agent_loop ===
def agent_loop(messages: list) -> str:
    rounds_without_todo = 0
    while True:
        # s06: compression pipeline
        microcompact(messages)
        if estimate_tokens(messages) > TOKEN_THRESHOLD:
            print("[auto-compact triggered]")
            messages[:] = auto_compact(messages)
        # s13: drain background notifications
        notifs = BG.drain()
        if notifs:
            txt = "\n".join(f"[bg:{n['task_id']}] {n['status']}: {n['result']}" for n in notifs)
            messages.append({"role": "user", "content": f"<background-results>\n{txt}\n</background-results>"})
        # s15: check lead inbox
        inbox = BUS.read_inbox("lead")
        if inbox:
            messages.append({"role": "user", "content": f"<inbox>{json.dumps(inbox, indent=2)}</inbox>"})

        # OpenAI 兼容请求：system + 历史消息 + function tools。
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": SYSTEM}, *messages],
            tools=TOOLS, max_tokens=8000,
        )

        msg = response.choices[0].message
        assistant_msg = {
            "role": "assistant",
            "content": msg.content or "",
        }
        if msg.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments or "{}",
                    },
                }
                for tc in msg.tool_calls
            ]
        messages.append(assistant_msg)

        if not msg.tool_calls:
            return msg.content or ""

        used_todo = False
        manual_compress = False

        for tool_call in msg.tool_calls:
            name = tool_call.function.name
            if name == "compress":
                manual_compress = True
            handler = TOOL_HANDLERS.get(name)

            # 工具参数文本必须先解析，避免 JSON 格式异常导致循环中断。
            try:
                parsed_args = json.loads(tool_call.function.arguments or "{}")
                if not isinstance(parsed_args, dict):
                    raise ValueError("Arguments must be a JSON object")
            except Exception as e:
                output = f"Error: Invalid tool arguments: {e}"
            else:
                try:
                    output = handler(**parsed_args) if handler else f"Unknown tool: {name}"
                except Exception as e:
                    output = f"Error: {e}"

            print(f"> {name}:")
            print(str(output)[:200])
            print(f"< /{name}")

            # 使用 role=tool 回注，让模型读取工具结果继续推理。
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(output),
                }
            )

            if name == "TodoWrite":
                used_todo = True

        # s03: nag reminder (only when todo workflow is active)
        rounds_without_todo = 0 if used_todo else rounds_without_todo + 1
        if TODO.has_open_items() and rounds_without_todo >= 3:
            messages.append({"role": "user", "content": "<reminder>Update your todos.</reminder>"})

        # s06: manual compress
        if manual_compress:
            print("[manual compact]")
            messages[:] = auto_compact(messages)
            return


# === SECTION: repl ===
if __name__ == "__main__":
    history = []
    while True:
        try:
            query = input("\033[36mminiClaudeCode >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        # 退出机制
        if query.strip().lower() in ("q", "exit", ""):
            break
        # 内置命令：/compact 手动触发压缩，/tasks 列出任务，/team 列出队友，/inbox 查看收件箱。
        if query.strip() == "/compact":
            if history:
                print("[manual compact via /compact]")
                history[:] = auto_compact(history)
            continue
        if query.strip() == "/tasks":
            print(TASK_MGR.list_all())
            continue
        if query.strip() == "/team":
            print(TEAM.list_all())
            continue
        if query.strip() == "/inbox":
            print(json.dumps(BUS.read_inbox("lead"), indent=2))
            continue
        history.append({"role": "user", "content": query})
        final_text = agent_loop(history)
        if final_text:
            print(final_text)
        print()
