"""Command-line interface for the calculator.

This module provides the CLI functionality for the calculator, including
argument parsing and the main entry point.
"""

import sys
from typing import List, Optional

from calculator.operations import add, subtract, multiply, divide


def parse_args(args: Optional[List[str]] = None) -> tuple:
    """Parse command-line arguments.

    Args:
        args: List of arguments to parse. If None, uses sys.argv.

    Returns:
        A tuple of (operation, a, b) where operation is a string and a, b are floats.

    Raises:
        ValueError: If arguments are invalid or missing.
    """
    if args is None:
        args = sys.argv[1:]
    
    if len(args) != 3:
        raise ValueError(
            f"Expected 3 arguments (operation, a, b), got {len(args)}: {args}"
        )
    
    operation, a_str, b_str = args
    
    try:
        a = float(a_str)
    except ValueError:
        raise ValueError(f"Invalid number for first operand: {a_str}")
    
    try:
        b = float(b_str)
    except ValueError:
        raise ValueError(f"Invalid number for second operand: {b_str}")
    
    return operation, a, b


def main(args: Optional[List[str]] = None) -> int:
    """Main entry point for the calculator CLI.

    Args:
        args: List of arguments to process. If None, uses sys.argv.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    operations = {
        "add": add,
        "subtract": subtract,
        "multiply": multiply,
        "divide": divide,
    }
    
    try:
        operation, a, b = parse_args(args)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        print_usage()
        return 1
    
    if operation not in operations:
        print(f"Error: Unknown operation '{operation}'", file=sys.stderr)
        print(f"Available operations: {', '.join(operations.keys())}", file=sys.stderr)
        return 1
    
    try:
        result = operations[operation](a, b)
        # Display as integer if result is a whole number
        if result == int(result):
            print(int(result))
        else:
            print(result)
        return 0
    except ZeroDivisionError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def print_usage() -> None:
    """Print usage information."""
    print("Usage: calculator <operation> <a> <b>", file=sys.stderr)
    print("Operations: add, subtract, multiply, divide", file=sys.stderr)
    print("", file=sys.stderr)
    print("Examples:", file=sys.stderr)
    print("  calculator add 5 3       # Output: 8", file=sys.stderr)
    print("  calculator subtract 5 3  # Output: 2", file=sys.stderr)
    print("  calculator multiply 5 3  # Output: 15", file=sys.stderr)
    print("  calculator divide 6 2    # Output: 3", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())