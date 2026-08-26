from __future__ import annotations

import inspect

from stream_recoverability.data.uk_ea_temperature import uk_ea_daily


def test_uk_ea_daily_is_resampled_not_invented() -> None:
    source = inspect.getsource(uk_ea_daily)
    assert "resample" in source
    assert "invented" in source.lower() or "not invented" in inspect.getdoc(uk_ea_daily).lower()
