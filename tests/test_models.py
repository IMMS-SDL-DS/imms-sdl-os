"""
src/database/models.py 기본 검증 테스트
실행: pytest tests/test_models.py -v
"""

import pytest
from pydantic import ValidationError

from src.database.models import (
    OperationType,
    Task,
    TransferParams,
    validate_operation_params,
)


def test_transfer_params_order_critical():
    """프로토콜 D-1: order_critical TRANSFER가 정상 검증되는지."""
    params = validate_operation_params(
        OperationType.TRANSFER,
        {"source": "ligand_sol", "dest": "metal_sol", "volume_ml": None, "order_critical": True},
    )
    assert isinstance(params, TransferParams)
    assert params.order_critical is True
    assert params.volume_ml is None


def test_heat_params_from_protocol():
    """프로토콜 D-3: HEAT 120°C, 24h."""
    params = validate_operation_params(
        OperationType.HEAT,
        {"vessel": "Vial_10mL", "temp_c": 120, "duration_h": 24, "mode": "static"},
    )
    assert params.temp_c == 120
    assert params.duration_h == 24


def test_centrifuge_params_invalid_missing_field():
    """필수 필드(rpm) 누락 시 검증 실패해야 함."""
    with pytest.raises(ValidationError):
        validate_operation_params(
            OperationType.CENTRIFUGE,
            {"vessel": "Conical_15mL", "duration_min": 2.5},  # rpm 누락
        )


def test_task_required_device_type():
    """Task.required_device_type()이 OPERATION_REQUIRED_DEVICE_TYPE과 일치하는지."""
    task = Task(
        task_id="exp_zrbtc_001_D-1",
        experiment_id="exp_zrbtc_001",
        phase="D",
        step_code="D-1",
        operation=OperationType.TRANSFER,
        parameters={"source": "ligand_sol", "dest": "metal_sol", "order_critical": True},
        order_critical=True,
    )
    assert task.required_device_type() == "liquid_handler"


def test_repeat_operation_params():
    """프로토콜 F-2~F-6 Washing 3회 반복(REPEAT) 파라미터 검증."""
    params = validate_operation_params(
        OperationType.REPEAT,
        {"start_step": "F-2", "end_step": "F-6", "count": 3, "solvent": "DMF"},
    )
    assert params.count == 3


def test_physical_operations_are_not_safely_retryable():
    """DISPENSE_SOLID 등 물리적 부작용이 있는 오퍼레이션은 자동 재시도하면 안 됨."""
    from src.database.models import is_safely_retryable

    dangerous_ops = [
        OperationType.DISPENSE_SOLID,
        OperationType.TRANSFER,
        OperationType.HEAT,
        OperationType.CENTRIFUGE,
        OperationType.DISPENSE,
    ]
    for op in dangerous_ops:
        assert not is_safely_retryable(op), f"{op}는 재시도 위험한데 안전하다고 분류됨"


def test_measurement_operations_are_safely_retryable():
    """VERIFY_MASS 등 측정/판독만 하는 오퍼레이션은 재시도해도 안전함."""
    from src.database.models import is_safely_retryable

    safe_ops = [
        OperationType.VERIFY_MASS,
        OperationType.ANALYZE_XRD,
        OperationType.ANALYZE_OM,
        OperationType.BALANCE_CHECK,
    ]
    for op in safe_ops:
        assert is_safely_retryable(op), f"{op}는 안전한데 재시도 불가로 분류됨"
