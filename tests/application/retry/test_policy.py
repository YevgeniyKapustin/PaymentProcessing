from application.exceptions import (
    PermanentProcessingError,
    TransientDependencyError,
)
from application.retry.policy import DispatchAction, RetryPolicy


def test_permanent_error_goes_to_dlq_on_first_attempt() -> None:
    action = RetryPolicy().action(0, PermanentProcessingError("bad"))
    assert action is DispatchAction.DLQ


def test_transient_retries_then_dlq() -> None:
    error = TransientDependencyError("timeout")
    policy = RetryPolicy()
    assert policy.action(0, error) is DispatchAction.RETRY
    assert policy.action(1, error) is DispatchAction.RETRY
    assert policy.action(2, error) is DispatchAction.DLQ


def test_generic_error_retries() -> None:
    assert RetryPolicy().action(0, RuntimeError("boom")) is DispatchAction.RETRY


def test_retry_delays_are_exponential() -> None:
    policy = RetryPolicy()
    assert policy.delay_seconds(0) == 1
    assert policy.delay_seconds(1) == 2
    assert policy.delay_seconds(2) == 4
    assert policy.delay_seconds(99) == 4
