import json
import threading
import time

from miniClaudeCode.core.config import (
    IDLE_TIMEOUT,
    POLL_INTERVAL,
    TASKS_DIR,
    WORKDIR,
)
from miniClaudeCode.tools import make_tool, run_bash, run_edit, run_read, run_write


class TeammateManager:
    def __init__(self, bus, task_mgr, client, model: str, team_dir):
        team_dir.mkdir(exist_ok=True)
        self.bus = bus
        self.task_mgr = task_mgr
        self.client = client
        self.model = model
        self.config_path = team_dir / "config.json"
        self.config = self._load()

    def _load(self) -> dict:
        if self.config_path.exists():
            return json.loads(self.config_path.read_text())
        return {"team_name": "default", "members": []}

    def _save(self):
        self.config_path.write_text(json.dumps(self.config, indent=2))

    def _find(self, name: str) -> dict:
        for member in self.config["members"]:
            if member["name"] == name:
                return member
        return None

    def _set_status(self, name: str, status: str):
        member = self._find(name)
        if member:
            member["status"] = status
            self._save()

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
        threading.Thread(
            target=self._loop,
            args=(name, role, prompt),
            daemon=True,
        ).start()
        return f"Spawned '{name}' (role: {role})"

    def _loop(self, name: str, role: str, prompt: str):
        team_name = self.config["team_name"]
        system_prompt = (
            f"You are '{name}', role: {role}, team: {team_name}, at {WORKDIR}. "
            "Use idle when done with current work. You may auto-claim tasks."
        )
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
            for _ in range(50):
                inbox = self.bus.read_inbox(name)
                for msg in inbox:
                    if msg.get("type") == "shutdown_request":
                        self._set_status(name, "shutdown")
                        return
                    messages.append({"role": "user", "content": json.dumps(msg)})

                try:
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "system", "content": system_prompt}, *messages],
                        tools=tools,
                        max_tokens=8000,
                    )
                except Exception:
                    self._set_status(name, "shutdown")
                    return

                msg = response.choices[0].message
                assistant = {"role": "assistant", "content": msg.content or ""}
                if msg.tool_calls:
                    assistant["tool_calls"] = [
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
                messages.append(assistant)

                if not msg.tool_calls:
                    break

                idle_requested = False
                for tool_call in msg.tool_calls:
                    call_name = tool_call.function.name
                    try:
                        parsed_args = json.loads(tool_call.function.arguments or "{}")
                        if not isinstance(parsed_args, dict):
                            raise ValueError("Arguments must be a JSON object")
                    except Exception as exc:
                        output = f"Error: Invalid tool arguments: {exc}"
                    else:
                        if call_name == "idle":
                            idle_requested = True
                            output = "Entering idle phase."
                        elif call_name == "claim_task":
                            output = self.task_mgr.claim(parsed_args["task_id"], name)
                        elif call_name == "send_message":
                            output = self.bus.send(name, parsed_args["to"], parsed_args["content"])
                        else:
                            dispatch = {
                                "bash": lambda **kw: run_bash(kw["command"]),
                                "read_file": lambda **kw: run_read(kw["path"]),
                                "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
                                "edit_file": lambda **kw: run_edit(
                                    kw["path"], kw["old_text"], kw["new_text"]
                                ),
                            }
                            output = dispatch.get(call_name, lambda **kw: "Unknown")(**parsed_args)

                    print(f"  [{name}] {call_name}: {str(output)[:120]}")
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": str(output),
                        }
                    )

                if idle_requested:
                    break

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
                for task_file in sorted(TASKS_DIR.glob("task_*.json")):
                    task = json.loads(task_file.read_text())
                    if (
                        task.get("status") == "pending"
                        and not task.get("owner")
                        and not task.get("blockedBy")
                    ):
                        unclaimed.append(task)

                if unclaimed:
                    task = unclaimed[0]
                    self.task_mgr.claim(task["id"], name)
                    if len(messages) <= 3:
                        messages.insert(
                            0,
                            {
                                "role": "user",
                                "content": (
                                    f"<identity>You are '{name}', role: {role}, team: {team_name}."
                                    "</identity>"
                                ),
                            },
                        )
                        messages.insert(
                            1,
                            {"role": "assistant", "content": f"I am {name}. Continuing."},
                        )
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"<auto-claimed>Task #{task['id']}: {task['subject']}\n"
                                f"{task.get('description', '')}</auto-claimed>"
                            ),
                        }
                    )
                    messages.append(
                        {
                            "role": "assistant",
                            "content": f"Claimed task #{task['id']}. Working on it.",
                        }
                    )
                    resume = True
                    break

            if not resume:
                self._set_status(name, "shutdown")
                return

            self._set_status(name, "working")

    def list_all(self) -> str:
        if not self.config["members"]:
            return "No teammates."
        lines = [f"Team: {self.config['team_name']}"]
        for member in self.config["members"]:
            lines.append(f"  {member['name']} ({member['role']}): {member['status']}")
        return "\n".join(lines)

    def member_names(self) -> list:
        return [member["name"] for member in self.config["members"]]
