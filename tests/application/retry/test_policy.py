from uuid import uuid4

from application.exceptions import (
    PaymentNotFound,
    PermanentProcessingError,
    TransientDependencyError,
)
from application.retry.policy import DispatchAction, RetryPolicy
from domain.exceptions import IllegalStatusTransitionError


def test_permanent_error_goes_to_dlq_on_first_attempt() -> None:
    action = RetryPolicy().decide_action(0, PermanentProcessingError("bad"))
    assert action is DispatchAction.DLQ


def test_transient_retries_then_dlq() -> None:
    error = TransientDependencyError("timeout")
    policy = RetryPolicy()
    assert policy.decide_action(0, error) is DispatchAction.RETRY
    assert policy.decide_action(1, error) is DispatchAction.RETRY
    assert policy.decide_action(2, error) is DispatchAction.DLQ


def test_generic_error_retries() -> None:
    assert RetryPolicy().decide_action(0, RuntimeError("boom")) is DispatchAction.RETRY


def test_domain_error_goes_to_dlq() -> None:
    error = IllegalStatusTransitionError("pending", "failed")
    assert RetryPolicy().decide_action(0, error) is DispatchAction.DLQ


def test_payment_not_found_goes_to_dlq() -> None:
    error = PaymentNotFound(uuid4())
    assert RetryPolicy().decide_action(0, error) is DispatchAction.DLQ


def test_retry_delays_are_exponential() -> None:
    policy = RetryPolicy()
    assert policy.compute_delay_seconds(0) == 1
    assert policy.compute_delay_seconds(1) == 2
    assert policy.compute_delay_seconds(2) == 4
    assert policy.compute_delay_seconds(99) == 4
