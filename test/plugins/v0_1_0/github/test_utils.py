from __future__ import annotations

from iambic.plugins.v0_1_0.github.utils import (
    IAMBIC_APPLY_ERROR_METADATA,
    is_iambic_apply_error,
)


def test_is_iambic_apply_error():
    expected_result = is_iambic_apply_error(f"xyz\n{IAMBIC_APPLY_ERROR_METADATA}")
    assert expected_result


def test_is_not_iambic_apply_error():
    expected_result = is_iambic_apply_error("xyz\n")
    assert not expected_result
