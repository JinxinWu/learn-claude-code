"""Calculator package - A CLI calculator supporting basic arithmetic operations.

This package provides both programmatic access to arithmetic operations
and a command-line interface for performing calculations.

Usage:
    # Programmatic usage
    from calculator import add, subtract, multiply, divide
    
    result = add(5, 3)  # 8
    
    # CLI usage
    $ python -m calculator add 5 3
    8
"""

from calculator.operations import add, subtract, multiply, divide

__version__ = "1.0.0"
__all__ = ["add", "subtract", "multiply", "divide"]