"""Entry point for running the calculator as a module.

This allows the calculator to be run with:
    python -m calculator <operation> <a> <b>
"""

import sys
from calculator.cli import main

if __name__ == "__main__":
    sys.exit(main())