import numpy as np
import pandas as pd
import pytest


def make_ohlcv(closes, start="2024-01-01", freq="1h") -> pd.DataFrame:
    closes = np.asarray(closes, dtype=float)
    index = pd.date_range(start, periods=len(closes), freq=freq, tz="UTC")
    opens = np.concatenate([[closes[0]], closes[:-1]])
    return pd.DataFrame(
        {
            "open": opens,
            "high": np.maximum(opens, closes) * 1.001,
            "low": np.minimum(opens, closes) * 0.999,
            "close": closes,
            "volume": 1.0,
        },
        index=index,
    )


@pytest.fixture
def ohlcv_factory():
    return make_ohlcv
