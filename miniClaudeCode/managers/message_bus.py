import json
import time

from miniClaudeCode.core.config import INBOX_DIR


class MessageBus:
    def __init__(self):
        INBOX_DIR.mkdir(parents=True, exist_ok=True)

    def send(
        self,
        sender: str,
        target: str,
        content: str,
        msg_type: str = "message",
        extra: dict = None,
    ) -> str:
        payload = {
            "type": msg_type,
            "from": sender,
            "content": content,
            "timestamp": time.time(),
        }
        if extra:
            payload.update(extra)

        with open(INBOX_DIR / f"{target}.jsonl", "a") as handle:
            handle.write(json.dumps(payload) + "\n")
        return f"Sent {msg_type} to {target}"

    def read_inbox(self, name: str) -> list:
        path = INBOX_DIR / f"{name}.jsonl"
        if not path.exists():
            return []

        messages = [json.loads(line) for line in path.read_text().strip().splitlines() if line]
        path.write_text("")
        return messages

    def broadcast(self, sender: str, content: str, names: list) -> str:
        count = 0
        for name in names:
            if name == sender:
                continue
            self.send(sender, name, content, "broadcast")
            count += 1
        return f"Broadcast to {count} teammates"
