import json
import time
import uuid

from miniClaudeCode.core.config import MESSAGES_DIR


def run_subagent(
    client,
    model: str,
    make_tool,
    run_bash,
    run_read,
    run_write,
    run_edit,
    prompt: str,
    agent_type: str = "Explore",
) -> str:
    def persist_messages(all_messages: list, final_text: str) -> None:
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
            pass

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
        sub_tools.extend(
            [
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
        )

    handlers = {
        "bash": lambda **kw: run_bash(kw["command"]),
        "read_file": lambda **kw: run_read(kw["path"]),
        "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
        "edit_file": lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
    }

    messages = [{"role": "user", "content": prompt}]
    final_text = ""

    for _ in range(30):
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a focused subagent."},
                *messages,
            ],
            tools=sub_tools,
            max_tokens=8000,
        )

        msg = response.choices[0].message
        final_text = msg.content or ""

        assistant = {"role": "assistant", "content": final_text}
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
            persist_messages(messages, final_text)
            return final_text or "(no summary)"

        for tool_call in msg.tool_calls:
            name = tool_call.function.name
            handler = handlers.get(name)

            try:
                parsed_args = json.loads(tool_call.function.arguments or "{}")
                if not isinstance(parsed_args, dict):
                    raise ValueError("Arguments must be a JSON object")
            except Exception as exc:
                output = f"Error: Invalid tool arguments: {exc}"
            else:
                try:
                    output = handler(**parsed_args) if handler else "Unknown tool"
                except Exception as exc:
                    output = f"Error: {exc}"

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(output)[:50000],
                }
            )

    persist_messages(messages, final_text)
    return final_text or "(subagent failed)"
