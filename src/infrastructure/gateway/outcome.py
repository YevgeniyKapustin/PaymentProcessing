from __future__ import annotations

import random


class RandomChargeOutcome:
    def __init__(self, success_rate: float) -> None:
        self._success_rate = success_rate

    def is_successful(self) -> bool:
        return random.random() < self._success_rate
