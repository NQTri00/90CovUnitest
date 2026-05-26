import pytest
from calculator_service import CalculatorService

class TestCalculatorService:

    @pytest.fixture
    def service(self):
        return CalculatorService()

    # ===== add tests =====

    def test_add_happy_path(self, service):
        """Unknown_add_001: Kiểm tra phép cộng hai số dương thông thường"""
        result = service.add(1.0, 2.0)
        assert result == 3.0

    def test_add_both_zero(self, service):
        """Unknown_add_002: Kiểm tra phép cộng với cả hai tham số bằng 0"""
        result = service.add(0.0, 0.0)
        assert result == 0.0

    def test_add_none_a_raises_type_error(self, service):
        """Unknown_add_003: Kiểm tra khi tham số a là None gây TypeError"""
        with pytest.raises(TypeError, match=r"unsupported operand type\(s\) for \+"):
            service.add(None, 2.0)

    def test_add_negative_and_positive(self, service):
        """Unknown_add_004: Kiểm tra phép cộng với số âm và số dương"""
        result = service.add(-5.0, 3.0)
        assert result == -2.0

    def test_add_floating_point(self, service):
        """Unknown_add_005: Kiểm tra phép cộng với số thập phân"""
        result = service.add(0.1, 0.2)
        assert abs(result - 0.3) < 1e-9

    # ===== divide tests =====

    def test_divide_happy_path(self, service):
        """Unknown_divide_001: Kiểm tra phép chia hai số dương thông thường"""
        result = service.divide(10.0, 2.0)
        assert result == 5.0

    def test_divide_zero_numerator(self, service):
        """Unknown_divide_002: Kiểm tra phép chia với tử số bằng 0"""
        result = service.divide(0.0, 5.0)
        assert result == 0.0

    def test_divide_by_zero_raises_value_error(self, service):
        """Unknown_divide_003: Kiểm tra phép chia với mẫu số bằng 0 gây ValueError"""
        with pytest.raises(ValueError, match="Cannot divide by zero"):
            service.divide(10.0, 0.0)

    def test_divide_negative_numerator(self, service):
        """Unknown_divide_004: Kiểm tra phép chia với số âm"""
        result = service.divide(-10.0, 2.0)
        assert result == -5.0

    def test_divide_non_integer_result(self, service):
        """Unknown_divide_005: Kiểm tra phép chia với kết quả không nguyên"""
        result = service.divide(7.0, 3.0)
        assert abs(result - 2.3333333333333335) < 1e-9