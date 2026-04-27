import subprocess
import threading
import uuid
from queue import Queue

from miniClaudeCode.core.config import WORKDIR


class BackgroundManager:
    def __init__(self):
        self.tasks = {}
        self.notifications = Queue()

    def run(self, command: str, timeout: int = 120) -> str:
        task_id = str(uuid.uuid4())[:8]
        self.tasks[task_id] = {"status": "running", "command": command, "result": None}
        threading.Thread(
            target=self._exec,
            args=(task_id, command, timeout),
            daemon=True,
        ).start()
        return f"Background task {task_id} started: {command[:80]}"

    def _exec(self, task_id: str, command: str, timeout: int):
        try:
            completed = subprocess.run(
                command,
                shell=True,
                cwd=WORKDIR,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = (completed.stdout + completed.stderr).strip()[:50000]
            self.tasks[task_id].update(
                {
                    "status": "completed",
                    "result": output or "(no output)",
                }
            )
        except Exception as exc:
            self.tasks[task_id].update({"status": "error", "result": str(exc)})

        self.notifications.put(
            {
                "task_id": task_id,
                "status": self.tasks[task_id]["status"],
                "result": self.tasks[task_id]["result"][:500],
            }
        )

    def check(self, task_id: str = None) -> str:
        if task_id:
            task = self.tasks.get(task_id)
            if not task:
                return f"Unknown: {task_id}"
            return f"[{task['status']}] {task.get('result') or '(running)'}"

        lines = [
            f"{tid}: [{meta['status']}] {meta['command'][:60]}"
            for tid, meta in self.tasks.items()
        ]
        return "\n".join(lines) if lines else "No bg tasks."

    def drain(self) -> list:
        notifications = []
        while not self.notifications.empty():
            notifications.append(self.notifications.get_nowait())
        return notifications
