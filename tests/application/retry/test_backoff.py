from pytest import MonkeyPatch

from application.retry.backoff import ExponentialDelay


def test_delay_doubles_until_cap() -> None:
    delay = ExponentialDelay(initial=1.0, cap=60.0, use_jitter=False)
    assert delay.delay_for(1) == 1.0
    assert delay.delay_for(2) == 2.0
    assert delay.delay_for(3) == 4.0
    assert delay.delay_for(7) == 60.0
    assert delay.delay_for(0) == 0.0


def test_jitter_scales_base_delay(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("application.retry.backoff.random.random", lambda: 0.0)
    delay = ExponentialDelay(initial=2.0, cap=60.0, use_jitter=True)
    assert delay.delay_for(1) == 1.0
