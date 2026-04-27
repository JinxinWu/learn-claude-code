"""Unit tests for calculator operations.

This module tests all arithmetic operations in the calculator.operations module.
"""

import pytest
from calculator.operations import add, subtract, multiply, divide


class TestAdd:
    """Tests for the add operation."""
    
    def test_add_positive_numbers(self):
        """Test adding two positive numbers."""
        assert add(5, 3) == 8
    
    def test_add_negative_numbers(self):
        """Test adding two negative numbers."""
        assert add(-5, -3) == -8
    
    def test_add_mixed_sign_numbers(self):
        """Test adding numbers with different signs."""
        assert add(-5, 3) == -2
        assert add(5, -3) == 2
    
    def test_add_zero(self):
        """Test adding zero."""
        assert add(5, 0) == 5
        assert add(0, 5) == 5
        assert add(0, 0) == 0
    
    def test_add_floats(self):
        """Test adding floating point numbers."""
        assert add(2.5, 3.5) == 6.0
        assert add(0.1, 0.2) == pytest.approx(0.3)
    
    def test_add_integer_and_float(self):
        """Test adding an integer and a float."""
        assert add(5, 2.5) == 7.5
        assert add(2.5, 5) == 7.5


class TestSubtract:
    """Tests for the subtract operation."""
    
    def test_subtract_positive_numbers(self):
        """Test subtracting two positive numbers."""
        assert subtract(5, 3) == 2
    
    def test_subtract_negative_numbers(self):
        """Test subtracting two negative numbers."""
        assert subtract(-5, -3) == -2
    
    def test_subtract_mixed_sign_numbers(self):
        """Test subtracting numbers with different signs."""
        assert subtract(-5, 3) == -8
        assert subtract(5, -3) == 8
    
    def test_subtract_zero(self):
        """Test subtracting zero."""
        assert subtract(5, 0) == 5
        assert subtract(0, 5) == -5
        assert subtract(0, 0) == 0
    
    def test_subtract_floats(self):
        """Test subtracting floating point numbers."""
        assert subtract(6.5, 2.5) == 4.0
        assert subtract(0.3, 0.1) == pytest.approx(0.2)
    
    def test_subtract_integer_and_float(self):
        """Test subtracting an integer and a float."""
        assert subtract(5, 2.5) == 2.5
        assert subtract(7.5, 5) == 2.5


class TestMultiply:
    """Tests for the multiply operation."""
    
    def test_multiply_positive_numbers(self):
        """Test multiplying two positive numbers."""
        assert multiply(5, 3) == 15
    
    def test_multiply_negative_numbers(self):
        """Test multiplying two negative numbers."""
        assert multiply(-5, -3) == 15
    
    def test_multiply_mixed_sign_numbers(self):
        """Test multiplying numbers with different signs."""
        assert multiply(-5, 3) == -15
        assert multiply(5, -3) == -15
    
    def test_multiply_by_zero(self):
        """Test multiplying by zero."""
        assert multiply(5, 0) == 0
        assert multiply(0, 5) == 0
        assert multiply(0, 0) == 0
    
    def test_multiply_by_one(self):
        """Test multiplying by one."""
        assert multiply(5, 1) == 5
        assert multiply(1, 5) == 5
    
    def test_multiply_floats(self):
        """Test multiplying floating point numbers."""
        assert multiply(2.5, 2) == 5.0
        assert multiply(2.5, 2.5) == 6.25
    
    def test_multiply_integer_and_float(self):
        """Test multiplying an integer and a float."""
        assert multiply(4, 0.5) == 2.0
        assert multiply(0.5, 4) == 2.0


class TestDivide:
    """Tests for the divide operation."""
    
    def test_divide_positive_numbers(self):
        """Test dividing two positive numbers."""
        assert divide(6, 3) == 2
    
    def test_divide_negative_numbers(self):
        """Test dividing two negative numbers."""
        assert divide(-6, -3) == 2
    
    def test_divide_mixed_sign_numbers(self):
        """Test dividing numbers with different signs."""
        assert divide(-6, 3) == -2
        assert divide(6, -3) == -2
    
    def test_divide_zero_by_number(self):
        """Test dividing zero by a number."""
        assert divide(0, 5) == 0
    
    def test_divide_by_zero_raises_error(self):
        """Test that dividing by zero raises ZeroDivisionError."""
        with pytest.raises(ZeroDivisionError, match="Cannot divide by zero"):
            divide(5, 0)
        
        with pytest.raises(ZeroDivisionError):
            divide(0, 0)
    
    def test_divide_floats(self):
        """Test dividing floating point numbers."""
        assert divide(5.0, 2.0) == 2.5
        assert divide(1.0, 2.0) == 0.5
    
    def test_divide_integer_and_float(self):
        """Test dividing an integer and a float."""
        assert divide(5, 2.0) == 2.5
        assert divide(7.5, 2.5) == 3.0
    
    def test_divide_non_integer_result(self):
        """Test division that results in a non-integer."""
        assert divide(10, 3) == pytest.approx(3.333333, rel=1e-5)
        assert divide(1, 3) == pytest.approx(0.333333, rel=1e-5)