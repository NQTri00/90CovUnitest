import math
import pytest
from unittest.mock import MagicMock, patch
from calculator_service import CalculatorService


@pytest.fixture
def calculator_service():
    return CalculatorService()


class TestCalculatorService:
    """Test suite for CalculatorService."""

    def test_add_positive_numbers(self, calculator_service):
        """Kiểm tra phép cộng hai số dương hợp lệ"""
        result = calculator_service.add(2.5, 3.5)
        assert result == 6.0

    def test_add_with_negative_number(self, calculator_service):
        """Kiểm tra phép cộng với số âm"""
        result = calculator_service.add(-5.0, 10.0)
        assert result == 5.0

    def test_add_with_zero(self, calculator_service):
        """Kiểm tra phép cộng với số không"""
        result = calculator_service.add(0.0, 0.0)
        assert result == 0.0

    def test_add_large_numbers(self, calculator_service):
        """Kiểm tra phép cộng với giá trị cực lớn"""
        result = calculator_service.add(1e+308, 1e+308)
        assert result == float('inf') or not math.isfinite(result)

    def test_add_small_floating_point(self, calculator_service):
        """Kiểm tra phép cộng với số thập phân nhỏ xấp xỉ không"""
        result = calculator_service.add(1e-323, -1e-323)
        assert result == 0.0 or abs(result) < 1e-300

    def test_divide_positive_numbers(self, calculator_service):
        """Kiểm tra phép chia hai số dương hợp lệ"""
        result = calculator_service.divide(10.0, 2.0)
        assert result == 5.0

    def test_divide_with_decimal_result(self, calculator_service):
        """Kiểm tra phép chia với kết quả là số thập phân"""
        result = calculator_service.divide(7.0, 3.0)
        assert abs(result - 2.3333333333333335) < 1e-9

    def test_divide_by_zero_raises_value_error(self, calculator_service):
        """Kiểm tra phép chia cho số không - ném ValueError"""
        with pytest.raises(ValueError) as exc_info:
            calculator_service.divide(5.0, 0.0)
        assert str(exc_info.value) == "Cannot divide by zero"

    def test_divide_zero_by_positive(self, calculator_service):
        """Kiểm tra phép chia 0 cho số dương"""
        result = calculator_service.divide(0.0, 5.0)
        assert result == 0.0

    def test_divide_negative_by_positive(self, calculator_service):
        """Kiểm tra phép chia số âm cho số dương"""
        result = calculator_service.divide(-10.0, 2.0)
        assert result == -5.0

    def test_divide_large_dividend_causes_overflow(self, calculator_service):
        """Kiểm tra phép chia với số bị chia quá lớn gây overflow"""
        result = calculator_service.divide(1e+308, 0.1)
        assert result == float('inf') or not math.isfinite(result)