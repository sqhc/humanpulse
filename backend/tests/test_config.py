from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import INSECURE_DEFAULTS, Settings


def test_cors_origins_parsed_into_list() -> None:
    settings = Settings(cors_origins="http://a.test, http://b.test ,")
    assert settings.cors_origin_list == ["http://a.test", "http://b.test"]


def test_prod_rejects_default_admin_key() -> None:
    insecure = sorted(INSECURE_DEFAULTS)[0]
    with pytest.raises(ValidationError):
        Settings(env="prod", admin_api_key=insecure)


def test_prod_accepts_strong_admin_key() -> None:
    settings = Settings(env="production", admin_api_key="a-very-long-random-key")
    assert settings.is_prod is True


def test_dedup_thresholds_are_validated() -> None:
    with pytest.raises(ValidationError):
        Settings(vector_dup_threshold=1.5)
    with pytest.raises(ValidationError):
        Settings(simhash_hamming_threshold=99)
