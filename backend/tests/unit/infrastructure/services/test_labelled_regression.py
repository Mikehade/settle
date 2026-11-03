"""Regression suite: every labelled dispute's proposal must gate exactly
as expected. Pins the safety layer across all 3 types / 3 outcomes."""
import pytest

from src.infrastructure.services.executor import PayPalExecutor
from tests.fixtures.labelled_disputes import LABELLED_CASES
from tests.unit.infrastructure.services.test_executor import FakePayPalClient


@pytest.mark.parametrize("label,case_file,decision,expected_gate", LABELLED_CASES, ids=[c[0] for c in LABELLED_CASES])
async def test_labelled_case_gates_as_expected(label, case_file, decision, expected_gate):
    executor = PayPalExecutor(FakePayPalClient(), confidence_threshold=0.8, human_in_loop_amount=200.0, partial_refund_ceiling=150.0)
    result = await executor.execute(case_file, dict(decision))
    assert result["gate"] == expected_gate.value, f"{label}: expected {expected_gate.value}, got {result['gate']} ({result.get('gate_reason')})"
