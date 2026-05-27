#!/usr/bin/env python3
"""Generate SWE-bench prediction files using this repository's mini agent."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Iterable

from datasets import load_dataset

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents import miniClaudeCode as mcc


DEFAULT_DATASET = "princeton-nlp/SWE-bench_Lite"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate SWE-bench predictions from miniClaudeCode inference output."
    )
    parser.add_argument(
        "--dataset-name",
        default=DEFAULT_DATASET,
        help=f"HF dataset name (default: {DEFAULT_DATASET})",
    )
    parser.add_argument("--split", default="test", help="Dataset split")
    parser.add_argument(
        "--instance-ids",
        nargs="+",
        default=None,
        help="Specific SWE-bench instance IDs",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Take first N instances after filtering (0 means no limit)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("predictions/miniClaudeCode.swebench_lite.json"),
        help="Output predictions path (.json)",
    )
    parser.add_argument(
        "--engine",
        choices=["subagent", "agent-loop"],
        default="subagent",
        help="Inference engine from miniClaudeCode",
    )
    parser.add_argument(
        "--model-name",
        default=None,
        help="Value for model_name_or_path in prediction rows",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip model inference and write empty model_patch values",
    )
    parser.add_argument(
        "--max-problem-chars",
        type=int,
        default=12000,
        help="Truncate long problem statements",
    )
    parser.add_argument(
        "--raw-output-dir",
        type=Path,
        default=None,
        help="Optional directory to save raw model outputs by instance ID",
    )
    return parser.parse_args()


def select_instances(dataset_name: str, split: str, instance_ids: list[str] | None, limit: int) -> list[dict]:
    ds = load_dataset(dataset_name, split=split)
    rows = [dict(row) for row in ds]

    if instance_ids:
        wanted = set(instance_ids)
        rows = [row for row in rows if row["instance_id"] in wanted]
        found = {row["instance_id"] for row in rows}
        missing = sorted(wanted - found)
        if missing:
            raise ValueError(f"Unknown instance IDs in dataset: {', '.join(missing)}")

    if limit > 0:
        rows = rows[:limit]

    return rows


def extract_patch(text: str) -> str:
    if not text:
        return ""

    # Prefer fenced diff/patch blocks if they exist.
    fence = re.search(r"```(?:diff|patch)\s*\n(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        return sanitize_unified_diff(fence.group(1))

    # Then try generic fenced blocks but only keep those that include a diff.
    for m in re.finditer(r"```\s*\n(.*?)```", text, flags=re.DOTALL):
        candidate = sanitize_unified_diff(m.group(1))
        if candidate:
            return candidate

    # Fall back to the first unified diff marker.
    candidate = sanitize_unified_diff(text)
    if candidate:
        return candidate

    # Accept raw patches that start with file headers.
    if text.lstrip().startswith("--- ") and "\n+++ " in text:
        return text.strip() + "\n"

    return ""


def extract_last_diff_block(text: str) -> str:
    if not text:
        return ""
    blocks = split_unified_diff_blocks(text)
    if not blocks:
        return ""
    return blocks[-1].strip() + "\n"


def split_unified_diff_blocks(text: str) -> list[str]:
    allowed_prefixes = (
        "diff --git ",
        "index ",
        "--- ",
        "+++ ",
        "@@",
        "new file mode ",
        "deleted file mode ",
        "old mode ",
        "new mode ",
        "similarity index ",
        "rename from ",
        "rename to ",
        "Binary files ",
        "GIT binary patch",
        "literal ",
        "delta ",
        "\\ No newline at end of file",
        "+",
        "-",
        " ",
    )

    blocks = []
    current = []
    in_block = False

    for line in text.splitlines():
        if line.startswith("diff --git "):
            if current:
                blocks.append("\n".join(current).strip())
            current = [line]
            in_block = True
            continue

        if not in_block:
            continue

        if line == "":
            current.append(line)
            continue

        if line.startswith(allowed_prefixes):
            current.append(line)
            continue

        # Chatter or non-diff text ends current block.
        if current:
            blocks.append("\n".join(current).strip())
        current = []
        in_block = False

    if current:
        blocks.append("\n".join(current).strip())

    # Keep only blocks that look like real patches.
    return [b for b in blocks if "\n--- " in b and "\n+++ " in b]


def sanitize_unified_diff(text: str) -> str:
    blocks = split_unified_diff_blocks(text)
    if not blocks:
        return ""
    return "\n\n".join(blocks).strip() + "\n"


def build_prompt(row: dict, max_problem_chars: int) -> str:
    problem = str(row.get("problem_statement", ""))[:max_problem_chars]
    hint = (row.get("hints_text") or "").strip()

    parts = [
        "You are generating a SWE-bench model patch.",
        "Return ONLY a valid unified git diff patch. No prose.",
        "If you cannot produce a patch, return an empty string.",
        "",
        f"instance_id: {row['instance_id']}",
        f"repo: {row.get('repo', '')}",
        f"base_commit: {row.get('base_commit', '')}",
        "",
        "problem_statement:",
        problem,
    ]

    if hint:
        parts.extend(["", "hints_text:", hint])

    return "\n".join(parts)


def run_inference(prompt: str, engine: str) -> str:
    if engine == "subagent":
        return mcc.run_subagent(prompt, agent_type="Explore")
    messages = [{"role": "user", "content": prompt}]
    return mcc.agent_loop(messages)


def infer_with_trace(prompt: str, engine: str) -> tuple[str, str]:
    """Run inference and return (raw_output, transcript_text_fallback)."""
    if engine != "subagent":
        return run_inference(prompt, engine), ""

    messages_dir = Path(".messages")
    before = set(messages_dir.glob("subagent_*.json")) if messages_dir.exists() else set()
    raw = run_inference(prompt, engine)

    # Give the logger a tiny window to flush the transcript file.
    time.sleep(0.1)

    if not messages_dir.exists():
        return raw, ""

    after = set(messages_dir.glob("subagent_*.json"))
    new_files = sorted(after - before, key=lambda p: p.stat().st_mtime)
    if not new_files:
        return raw, ""

    latest = new_files[-1]
    try:
        payload = json.loads(latest.read_text())
    except Exception:
        return raw, ""

    messages = payload.get("messages", [])
    chunks = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str) and content:
            chunks.append(content)
    return raw, "\n\n".join(chunks)


def build_predictions(
    rows: Iterable[dict],
    engine: str,
    model_name: str,
    dry_run: bool,
    max_problem_chars: int,
    raw_output_dir: Path | None,
) -> list[dict]:
    predictions = []
    rows = list(rows)
    total = len(rows)

    for idx, row in enumerate(rows, start=1):
        iid = row["instance_id"]
        print(f"[{idx}/{total}] running {iid}")

        if dry_run:
            raw = ""
            trace = ""
            patch = ""
        else:
            prompt = build_prompt(row, max_problem_chars=max_problem_chars)
            raw, trace = infer_with_trace(prompt, engine=engine)
            patch = extract_patch(raw)
            if not patch:
                patch = extract_last_diff_block(raw)
            if not patch:
                patch = extract_patch(trace)
            if not patch:
                patch = extract_last_diff_block(trace)

        if raw_output_dir is not None:
            raw_output_dir.mkdir(parents=True, exist_ok=True)
            (raw_output_dir / f"{iid}.txt").write_text(raw)
            if trace:
                (raw_output_dir / f"{iid}.trace.txt").write_text(trace)

        if not patch:
            print(f"  warning: empty patch for {iid}")

        predictions.append(
            {
                "instance_id": iid,
                "model_name_or_path": model_name,
                "model_patch": patch,
            }
        )

    return predictions


def main() -> None:
    args = parse_args()
    model_name = args.model_name or mcc.MODEL

    rows = select_instances(
        dataset_name=args.dataset_name,
        split=args.split,
        instance_ids=args.instance_ids,
        limit=args.limit,
    )
    if not rows:
        raise ValueError("No dataset rows selected. Check --instance-ids/--limit.")

    predictions = build_predictions(
        rows=rows,
        engine=args.engine,
        model_name=model_name,
        dry_run=args.dry_run,
        max_problem_chars=args.max_problem_chars,
        raw_output_dir=args.raw_output_dir,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(predictions, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {len(predictions)} predictions -> {args.output}")


if __name__ == "__main__":
    main()
