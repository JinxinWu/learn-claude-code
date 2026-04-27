#!/usr/bin/env python3
"""Legacy entrypoint for miniClaudeCode.

The full implementation now lives under the miniClaudeCode package.
Run either:
  - python -m miniClaudeCode
  - uv run agents/miniClaudeCode.py
"""

from miniClaudeCode.app import main


if __name__ == "__main__":
    main()
