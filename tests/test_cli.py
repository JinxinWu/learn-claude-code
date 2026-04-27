"""Tests for the calculator CLI.

This module tests the command-line interface functionality including
argument parsing and the main function.
"""

import pytest
from io import StringIO
from calculator.cli import parse_args, main, print_usage


class TestParseArgs:
    """Tests for argument parsing."""
    
    def test_parse_args_valid(self):
        """Test parsing valid arguments."""
        operation, a, b = parse_args(["add", "5", "3"])
        assert operation == "add"
        assert a == 5.0
        assert b == 3.0
    
    def test_parse_args_negative_numbers(self):
        """Test parsing negative numbers."""
        operation, a, b = parse_args(["add", "-5", "-3"])
        assert operation == "add"
        assert a == -5.0
        assert b == -3.0
    
    def test_parse_args_floats(self):
        """Test parsing floating point numbers."""
        operation, a, b = parse_args(["multiply", "2.5", "4.0"])
        assert operation == "multiply"
        assert a == 2.5
        assert b == 4.0
    
    def test_parse_args_too_few_arguments(self):
        """Test that too few arguments raises ValueError."""
        with pytest.raises(ValueError, match="Expected 3 arguments"):
            parse_args(["add", "5"])
        
        with pytest.raises(ValueError, match="Expected 3 arguments"):
            parse_args(["add"])
        
        with pytest.raises(ValueError, match="Expected 3 arguments"):
            parse_args([])
    
    def test_parse_args_too_many_arguments(self):
        """Test that too many arguments raises ValueError."""
        with pytest.raises(ValueError, match="Expected 3 arguments"):
            parse_args(["add", "5", "3", "2"])
    
    def test_parse_args_invalid_number_a(self):
        """Test that invalid first number raises ValueError."""
        with pytest.raises(ValueError, match="Invalid number for first operand"):
            parse_args(["add", "abc", "3"])
    
    def test_parse_args_invalid_number_b(self):
        """Test that invalid second number raises ValueError."""
        with pytest.raises(ValueError, match="Invalid number for second operand"):
            parse_args(["add", "5", "xyz"])
    
    def test_parse_args_scientific_notation(self):
        """Test parsing numbers in scientific notation."""
        operation, a, b = parse_args(["multiply", "1e2", "2.5e-1"])
        assert a == 100.0
        assert b == 0.25


class TestMain:
    """Tests for the main function."""
    
    def test_main_add(self, capsys):
        """Test the add operation through main."""
        exit_code = main(["add", "5", "3"])
        captured = capsys.readouterr()
        assert exit_code == 0
        assert captured.out.strip() == "8"
    
    def test_main_subtract(self, capsys):
        """Test the subtract operation through main."""
        exit_code = main(["subtract", "5", "3"])
        captured = capsys.readouterr()
        assert exit_code == 0
        assert captured.out.strip() == "2"
    
    def test_main_multiply(self, capsys):
        """Test the multiply operation through main."""
        exit_code = main(["multiply", "5", "3"])
        captured = capsys.readouterr()
        assert exit_code == 0
        assert captured.out.strip() == "15"
    
    def test_main_divide(self, capsys):
        """Test the divide operation through main."""
        exit_code = main(["divide", "6", "2"])
        captured = capsys.readouterr()
        assert exit_code == 0
        assert captured.out.strip() == "3"
    
    def test_main_divide_float_result(self, capsys):
        """Test division with float result."""
        exit_code = main(["divide", "5", "2"])
        captured = capsys.readouterr()
        assert exit_code == 0
        assert captured.out.strip() == "2.5"
    
    def test_main_divide_by_zero(self, capsys):
        """Test division by zero returns error."""
        exit_code = main(["divide", "5", "0"])
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "Cannot divide by zero" in captured.err
    
    def test_main_unknown_operation(self, capsys):
        """Test unknown operation returns error."""
        exit_code = main(["power", "5", "3"])
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "Unknown operation" in captured.err
    
    def test_main_invalid_arguments(self, capsys):
        """Test invalid arguments return error."""
        exit_code = main(["add", "5"])
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "Error:" in captured.err
    
    def test_main_integer_output(self, capsys):
        """Test that whole number results are displayed as integers."""
        exit_code = main(["divide", "6", "3"])
        captured = capsys.readouterr()
        assert exit_code == 0
        assert captured.out.strip() == "2"
        assert "." not in captured.out.strip()
    
    def test_main_float_output(self, capsys):
        """Test that non-integer results show decimal point."""
        exit_code = main(["divide", "5", "3"])
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "." in captured.out.strip()
    
    def test_main_negative_numbers(self, capsys):
        """Test operations with negative numbers."""
        exit_code = main(["add", "-5", "-3"])
        captured = capsys.readouterr()
        assert exit_code == 0
        assert captured.out.strip() == "-8"


class TestPrintUsage:
    """Tests for the print_usage function."""
    
    def test_print_usage_output(self, capsys):
        """Test that print_usage outputs to stderr."""
        print_usage()
        captured = capsys.readouterr()
        assert "Usage:" in captured.err
        assert "add" in captured.err
        assert "subtract" in captured.err
        assert "multiply" in captured.err
        assert "divide" in captured.err
        assert "Examples:" in captured.err