#!/usr/bin/env python3
"""
CLI Calculator - A simple command-line calculator

Usage:
    python calculator.py <operation> <num1> <num2>

Operations:
    add         - Addition
    subtract    - Subtraction
    multiply    - Multiplication
    divide      - Division

Examples:
    python calculator.py add 5 3
    python calculator.py divide 10 2
"""

import sys


def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b


def subtract(a: float, b: float) -> float:
    """Subtract b from a."""
    return a - b


def multiply(a: float, b: float) -> float:
    """Multiply two numbers."""
    return a * b


def divide(a: float, b: float) -> float:
    """Divide a by b."""
    if b == 0:
        raise ValueError("Error: Division by zero is not allowed.")
    return a / b


def main():
    """Main entry point for the CLI calculator."""
    if len(sys.argv) != 4:
        print("Usage: python calculator.py <operation> <num1> <num2>")
        print("\nOperations: add, subtract, multiply, divide")
        print("Example: python calculator.py add 5 3")
        sys.exit(1)

    operation = sys.argv[1].lower()

    # Map operations to functions
    operations = {
        "add": add,
        "subtract": subtract,
        "multiply": multiply,
        "divide": divide,
    }

    if operation not in operations:
        print(f"Error: Unknown operation '{operation}'")
        print("Available operations: add, subtract, multiply, divide")
        sys.exit(1)

    try:
        num1 = float(sys.argv[2])
        num2 = float(sys.argv[3])
    except ValueError:
        print("Error: Both arguments must be valid numbers.")
        sys.exit(1)

    try:
        result = operations[operation](num1, num2)
        # Display clean result (no decimal if integer)
        if result.is_integer():
            print(f"Result: {int(result)}")
        else:
            print(f"Result: {result}")
    except ValueError as e:
        print(e)
        sys.exit(1)


if __name__ == "__main__":
    main()