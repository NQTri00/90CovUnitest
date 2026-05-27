import pytest
from unittest.mock import MagicMock, patch
from calculator_service import CalculatorService  # assuming this module exists

@pytest.fixture
def service():
    """Fixture to create a CalculatorService instance."""
    return CalculatorService()

class TestCalculatorService:
    """Unit tests for CalculatorService."""

    # ---------- add method tests ----------

    def test_add_positive_numbers(self, service):
        """CalculatorService_add_001: Add two positive floats."""
        result = service.add(10.0, 20.5)
        assert result == 30.5

    def test_add_negative_and_positive(self, service):
        """CalculatorService_add_002: Add negative and positive floats."""
        result = service.add(-5.0, 3.0)
        assert result == -2.0

    def test_add_zeros(self, service):
        """CalculatorService_add_003: Add two zeros."""
        result = service.add(0.0, 0.0)
        assert result == 0.0

    def test_add_small_decimals(self, service):
        """CalculatorService_add_004: Add very small floats (precision)."""
        result = service.add(0.0001, 0.0002)
        # Use approx to allow floating point tolerance
        assert result == pytest.approx(0.0003, rel=1e-9)

    # ---------- divide method tests ----------

    def test_divide_positive_numbers(self, service):
        """CalculatorService_divide_001: Divide two positive floats."""
        result = service.divide(10.0, 2.0)
        assert result == 5.0

    def test_divide_negative_by_positive(self, service):
        """CalculatorService_divide_002: Divide negative by positive."""
        result = service.divide(-10.0, 2.0)
        assert result == -5.0

    def test_divide_zero_by_positive(self, service):
        """CalculatorService_divide_003: Divide zero by positive."""
        result = service.divide(0.0, 5.0)
        assert result == 0.0

    def test_divide_by_very_small_number(self, service):
        """CalculatorService_divide_004: Divide by a very small non-zero number."""
        result = service.divide(1.0, 1e-10)
        assert result == 1e10

    def test_divide_by_zero_raises_value_error(self, service):
        """CalculatorService_divide_005: Division by zero raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            service.divide(10.0, 0.0)
        assert str(exc_info.value) == "Cannot divide by zero"