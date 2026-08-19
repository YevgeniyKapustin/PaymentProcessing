from pytest import MonkeyPatch

from application.retry.backoff import ExponentialDelay


def test_delay_doubles_until_cap() -> None:
    delay = ExponentialDelay(initial=1.0, cap=60.0, jitter=False)
    assert delay.seconds(1) == 1.0
    assert delay.seconds(2) == 2.0
    assert delay.seconds(3) == 4.0
    assert delay.seconds(7) == 60.0
    assert delay.seconds(0) == 0.0


def test_jitter_scales_base_delay(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("application.retry.backoff.random.random", lambda: 0.0)
    delay = ExponentialDelay(initial=2.0, cap=60.0, jitter=True)
    assert delay.seconds(1) == 1.0
