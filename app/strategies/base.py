from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from app.schemas.signal import SignalContract


class Strategy(ABC):
    name: str

    @abstractmethod
    def generate(self, symbol: str, timeframe: str, candles: pd.DataFrame) -> SignalContract:
        raise NotImplementedError
