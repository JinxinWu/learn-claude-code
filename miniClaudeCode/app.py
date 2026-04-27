import json

from miniClaudeCode.core.compression import auto_compact, estimate_tokens, microcompact
from miniClaudeCode.core.config import (
    MODEL,
    SKILLS_DIR,
    TEAM_DIR,
    TOKEN_THRESHOLD,
    VALID_MSG_TYPES,
    WORKDIR,
    build_client,
)
from miniClaudeCode.core.protocols import handle_plan_review, handle_shutdown_request
from miniClaudeCode.core.subagent import run_subagent
from miniClaudeCode.managers import (
    BackgroundManager,
    MessageBus,
    SkillLoader,
    TaskManager,
    TodoManager,
)
from miniClaudeCode.managers.teammates import TeammateManager
from miniClaudeCode.tools import make_tool, run_bash, run_edit, run_read, run_write


class MiniClaudeCodeApp:
    def __init__(self):
        self.client = build_client()
        self.todo = TodoManager()
        self.skills = SkillLoader(SKILLS_DIR)
        self.task_mgr = TaskManager()
        self.bg = BackgroundManager()
        self.bus = MessageBus()
        self.team = TeammateManager(
            bus=self.bus,
            task_mgr=self.task_mgr,
            client=self.client,
            model=MODEL,
            team_dir=TEAM_DIR,
        )

    @property
    def system_prompt(self) -> str:
        return (
            f"You are a coding agent at {WORKDIR}. Use tools to solve tasks.\n"
            "Prefer task_create/task_update/task_list for multi-step work. "
            "Use TodoWrite for short checklists.\n"
            "Use task for subagent delegation. Use load_skill for specialized knowledge.\n"
            f"Skills: {self.skills.descriptions()}"
        )

    def build_tool_handlers(self) -> dict:
        return {
            "bash": lambda **kw: run_bash(kw["command"]),
            "read_file": lambda **kw: run_read(kw["path"], kw.get("limit")),
            "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
            "edit_file": lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
            "TodoWrite": lambda **kw: self.todo.update(kw["items"]),
            "task": lambda **kw: run_subagent(
                client=self.client,
                model=MODEL,
                make_tool=make_tool,
                run_bash=run_bash,
                run_read=run_read,
                run_write=run_write,
                run_edit=run_edit,
                prompt=kw["prompt"],
                agent_type=kw.get("agent_type", "Explore"),
            ),
            "load_skill": lambda **kw: self.skills.load(kw["name"]),
            "compress": lambda **kw: "Compressing...",
            "background_run": lambda **kw: self.bg.run(kw["command"], kw.get("timeout", 120)),
            "check_background": lambda **kw: self.bg.check(kw.get("task_id")),
            "task_create": lambda **kw: self.task_mgr.create(kw["subject"], kw.get("description", "")),
            "task_get": lambda **kw: self.task_mgr.get(kw["task_id"]),
            "task_update": lambda **kw: self.task_mgr.update(
                kw["task_id"], kw.get("status"), kw.get("add_blocked_by"), kw.get("remove_blocked_by")
            ),
            "task_list": lambda **kw: self.task_mgr.list_all(),
            "spawn_teammate": lambda **kw: self.team.spawn(kw["name"], kw["role"], kw["prompt"]),
            "list_teammates": lambda **kw: self.team.list_all(),
            "send_message": lambda **kw: self.bus.send("lead", kw["to"], kw["content"], kw.get("msg_type", "message")),
            "read_inbox": lambda **kw: json.dumps(self.bus.read_inbox("lead"), indent=2),
            "broadcast": lambda **kw: self.bus.broadcast("lead", kw["content"], self.team.member_names()),
            "shutdown_request": lambda **kw: handle_shutdown_request(self.bus, kw["teammate"]),
            "plan_approval": lambda **kw: handle_plan_review(self.bus, kw["request_id"], kw["approve"], kw.get("feedback", "")),
            "idle": lambda **kw: "Lead does not idle.",
            "claim_task": lambda **kw: self.task_mgr.claim(kw["task_id"], "lead"),
        }

    def build_tools(self) -> list:
        return [
            make_tool("bash", "Run a shell command.", {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}),
            make_tool("read_file", "Read file contents.", {"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["path"]}),
            make_tool("write_file", "Write content to file.", {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}),
            make_tool("edit_file", "Replace exact text in file.", {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}),
            make_tool("TodoWrite", "Update task tracking list.", {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {"content": {"type": "string"}, "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]}, "activeForm": {"type": "string"}}, "required": ["content", "status", "activeForm"]}}}, "required": ["items"]}),
            make_tool("task", "Spawn a subagent for isolated exploration or work.", {"type": "object", "properties": {"prompt": {"type": "string"}, "agent_type": {"type": "string", "enum": ["Explore", "general-purpose"]}}, "required": ["prompt"]}),
            make_tool("load_skill", "Load specialized knowledge by name.", {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}),
            make_tool("compress", "Manually compress conversation context.", {"type": "object", "properties": {}}),
            make_tool("background_run", "Run command in background thread.", {"type": "object", "properties": {"command": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["command"]}),
            make_tool("check_background", "Check background task status.", {"type": "object", "properties": {"task_id": {"type": "string"}}}),
            make_tool("task_create", "Create a persistent file task.", {"type": "object", "properties": {"subject": {"type": "string"}, "description": {"type": "string"}}, "required": ["subject"]}),
            make_tool("task_get", "Get task details by ID.", {"type": "object", "properties": {"task_id": {"type": "integer"}}, "required": ["task_id"]}),
            make_tool("task_update", "Update task status or dependencies.", {"type": "object", "properties": {"task_id": {"type": "integer"}, "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "deleted"]}, "add_blocked_by": {"type": "array", "items": {"type": "integer"}}, "remove_blocked_by": {"type": "array", "items": {"type": "integer"}}}, "required": ["task_id"]}),
            make_tool("task_list", "List all tasks.", {"type": "object", "properties": {}}),
            make_tool("spawn_teammate", "Spawn a persistent autonomous teammate.", {"type": "object", "properties": {"name": {"type": "string"}, "role": {"type": "string"}, "prompt": {"type": "string"}}, "required": ["name", "role", "prompt"]}),
            make_tool("list_teammates", "List all teammates.", {"type": "object", "properties": {}}),
            make_tool("send_message", "Send a message to a teammate.", {"type": "object", "properties": {"to": {"type": "string"}, "content": {"type": "string"}, "msg_type": {"type": "string", "enum": list(VALID_MSG_TYPES)}}, "required": ["to", "content"]}),
            make_tool("read_inbox", "Read and drain the lead's inbox.", {"type": "object", "properties": {}}),
            make_tool("broadcast", "Send message to all teammates.", {"type": "object", "properties": {"content": {"type": "string"}}, "required": ["content"]}),
            make_tool("shutdown_request", "Request a teammate to shut down.", {"type": "object", "properties": {"teammate": {"type": "string"}}, "required": ["teammate"]}),
            make_tool("plan_approval", "Approve or reject a teammate's plan.", {"type": "object", "properties": {"request_id": {"type": "string"}, "approve": {"type": "boolean"}, "feedback": {"type": "string"}}, "required": ["request_id", "approve"]}),
            make_tool("idle", "Enter idle state.", {"type": "object", "properties": {}}),
            make_tool("claim_task", "Claim a task from the board.", {"type": "object", "properties": {"task_id": {"type": "integer"}}, "required": ["task_id"]}),
        ]

    def agent_loop(self, messages: list) -> str:
        handlers = self.build_tool_handlers()
        tools = self.build_tools()
        rounds_without_todo = 0

        while True:
            microcompact(messages)
            if estimate_tokens(messages) > TOKEN_THRESHOLD:
                print("[auto-compact triggered]")
                messages[:] = auto_compact(self.client, MODEL, messages)

            notifications = self.bg.drain()
            if notifications:
                content = "\n".join(
                    f"[bg:{n['task_id']}] {n['status']}: {n['result']}"
                    for n in notifications
                )
                messages.append(
                    {
                        "role": "user",
                        "content": f"<background-results>\n{content}\n</background-results>",
                    }
                )

            inbox = self.bus.read_inbox("lead")
            if inbox:
                messages.append(
                    {
                        "role": "user",
                        "content": f"<inbox>{json.dumps(inbox, indent=2)}</inbox>",
                    }
                )

            response = self.client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "system", "content": self.system_prompt}, *messages],
                tools=tools,
                max_tokens=8000,
            )

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
                return msg.content or ""

            used_todo = False
            manual_compress = False

            for tool_call in msg.tool_calls:
                name = tool_call.function.name
                if name == "compress":
                    manual_compress = True

                handler = handlers.get(name)
                try:
                    parsed_args = json.loads(tool_call.function.arguments or "{}")
                    if not isinstance(parsed_args, dict):
                        raise ValueError("Arguments must be a JSON object")
                except Exception as exc:
                    output = f"Error: Invalid tool arguments: {exc}"
                else:
                    try:
                        output = handler(**parsed_args) if handler else f"Unknown tool: {name}"
                    except Exception as exc:
                        output = f"Error: {exc}"

                print(f"> {name}:")
                print(str(output)[:200])
                print(f"< /{name}")

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": str(output),
                    }
                )

                if name == "TodoWrite":
                    used_todo = True

            rounds_without_todo = 0 if used_todo else rounds_without_todo + 1
            if self.todo.has_open_items() and rounds_without_todo >= 3:
                messages.append({"role": "user", "content": "<reminder>Update your todos.</reminder>"})

            if manual_compress:
                print("[manual compact]")
                messages[:] = auto_compact(self.client, MODEL, messages)
                return ""

    def run_repl(self):
        history = []
        while True:
            try:
                query = input("\033[36mminiClaudeCode >> \033[0m")
            except (EOFError, KeyboardInterrupt):
                break

            if query.strip().lower() in ("q", "exit", ""):
                break

            if query.strip() == "/compact":
                if history:
                    print("[manual compact via /compact]")
                    history[:] = auto_compact(self.client, MODEL, history)
                continue

            if query.strip() == "/tasks":
                print(self.task_mgr.list_all())
                continue

            if query.strip() == "/team":
                print(self.team.list_all())
                continue

            if query.strip() == "/inbox":
                print(json.dumps(self.bus.read_inbox("lead"), indent=2))
                continue

            history.append({"role": "user", "content": query})
            final_text = self.agent_loop(history)
            if final_text:
                print(final_text)
            print()


def main():
    MiniClaudeCodeApp().run_repl()
