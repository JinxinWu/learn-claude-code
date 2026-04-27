"""Tests for the calculator package exports.

This module tests that the package correctly exports all operations
and maintains backwards compatibility.
"""

import pytest
from calculator import add, subtract, multiply, divide


class TestPackageExports:
    """Tests for package-level exports."""
    
    def test_add_is_callable(self):
        """Test that add is a callable function."""
        assert callable(add)
    
    def test_subtract_is_callable(self):
        """Test that subtract is a callable function."""
        assert callable(subtract)
    
    def test_multiply_is_callable(self):
        """Test that multiply is a callable function."""
        assert callable(multiply)
    
    def test_divide_is_callable(self):
        """Test that divide is a callable function."""
        assert callable(divide)
    
    def test_add_works(self):
        """Test that the exported add function works."""
        assert add(5, 3) == 8
    
    def test_subtract_works(self):
        """Test that the exported subtract function works."""
        assert subtract(5, 3) == 2
    
    def test_multiply_works(self):
        """Test that the exported multiply function works."""
        assert multiply(5, 3) == 15
    
    def test_divide_works(self):
        """Test that the exported divide function works."""
        assert divide(6, 2) == 3
    
    def test_all_exports(self):
        """Test that __all__ contains the expected exports."""
        from calculator import __all__
        assert "add" in __all__
        assert "subtract" in __all__
        assert "multiply" in __all__
        assert "divide" in __all__
        assert len(__all__) == 4
    
    def test_version_defined(self):
        """Test that the package version is defined."""
        from calculator import __version__
        assert __version__ == "1.0.0"


class TestBackwardsCompatibility:
    """Tests for backwards compatibility with the old calculator module."""
    
    def test_can_import_from_package(self):
        """Test that functions can be imported from the package."""
        from calculator import add, subtract, multiply, divide
        assert add(1, 2) == 3
        assert subtract(3, 2) == 1
        assert multiply(2, 3) == 6
        assert divide(6, 2) == 3
    
    def test_can_import_from_operations(self):
        """Test that functions can be imported directly from operations module."""
        from calculator.operations import add, subtract, multiply, divide
        assert add(1, 2) == 3
        assert subtract(3, 2) == 1
        assert multiply(2, 3) == 6
        assert divide(6, 2) == 3
    
    def test_cli_can_be_imported(self):
        """Test that the CLI module can be imported."""
        from calculator.cli import main
        assert callable(main)