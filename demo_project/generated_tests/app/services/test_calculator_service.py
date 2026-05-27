import pytest
from unittest.mock import MagicMock
from calculator_service import CalculatorService


@pytest.fixture
def calculator_service():
    return CalculatorService()


class TestCalculatorService:
    """Test suite for CalculatorService."""

    def test_add_positive_numbers(self, calculator_service):
        """Kiểm tra phép cộng hai số dương."""
        result = calculator_service.add(1.0, 2.0)
        assert result == 3.0

    def test_add_negative_and_positive(self, calculator_service):
        """Kiểm tra phép cộng với số âm và số dương."""
        result = calculator_service.add(-5.0, 3.0)
        assert result == -2.0

    def test_add_zeros(self, calculator_service):
        """Kiểm tra phép cộng với số 0."""
        result = calculator_service.add(0.0, 0.0)
        assert result == 0.0

    def test_divide_positive_numbers(self, calculator_service):
        """Kiểm tra phép chia hai số dương."""
        result = calculator_service.divide(10.0, 2.0)
        assert result == 5.0

    def test_divide_zero_dividend(self, calculator_service):
        """Kiểm tra phép chia với số bị chia bằng 0."""
        result = calculator_service.divide(0.0, 5.0)
        assert result == 0.0

    def test_divide_by_zero_raises_value_error(self, calculator_service):
        """Kiểm tra phép chia với số chia bằng 0, mong đợi ValueError."""
        with pytest.raises(ValueError) as exc_info:
            calculator_service.divide(5.0, 0.0)
        assert str(exc_info.value) == "Cannot divide by zero"