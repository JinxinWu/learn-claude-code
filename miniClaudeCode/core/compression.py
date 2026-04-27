import json
import time

from miniClaudeCode.core.config import TRANSCRIPT_DIR


def estimate_tokens(messages: list) -> int:
    return len(json.dumps(messages, default=str)) // 4


def microcompact(messages: list):
    tool_indices = []
    for index, msg in enumerate(messages):
        if msg.get("role") == "tool" and isinstance(msg.get("content"), str):
            tool_indices.append(index)

    if len(tool_indices) <= 3:
        return

    for index in tool_indices[:-3]:
        if len(messages[index]["content"]) > 100:
            messages[index]["content"] = "[cleared]"


def auto_compact(client, model: str, messages: list) -> list:
    TRANSCRIPT_DIR.mkdir(exist_ok=True)
    transcript = TRANSCRIPT_DIR / f"transcript_{int(time.time())}.jsonl"

    with open(transcript, "w") as handle:
        for msg in messages:
            handle.write(json.dumps(msg, default=str) + "\n")

    conv_text = json.dumps(messages, default=str)[-80000:]
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Summarize for continuity."},
            {"role": "user", "content": conv_text},
        ],
        max_tokens=2000,
    )

    summary = response.choices[0].message.content or "(no summary)"
    return [{"role": "user", "content": f"[Compressed. Transcript: {transcript}]\n{summary}"}]
