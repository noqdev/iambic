from __future__ import annotations

from unittest.mock import patch

import pytest

from iambic.plugins.v0_1_0.github.github_app import (
    calculate_signature,
    verify_signature,
)


@pytest.mark.parametrize(
    "secret, payload, expected_signature",
    [
        (
            "e9aec442806878a2ab7bc0676c515e03c1a8ab59",
            "fe11f072e13fd8deefe7d906e7d59a673f1d7a7d",
            "b611249a28989845434bfbe56cc4ebe0dfeb89161203157f82f43dd97de7eaa9",
        )
    ],
)
def test_calculate_signature(secret, payload, expected_signature):
    calculated_signature = calculate_signature(secret, payload)
    assert calculated_signature == expected_signature


@pytest.fixture()
def mock_github_webhook_secret():
    secret = "e9aec442806878a2ab7bc0676c515e03c1a8ab59"
    with patch(
        "iambic.plugins.v0_1_0.github.github_app.get_app_webhook_secret_as_lambda_context",
        autospec=True,
    ) as _mock_github_webhook_secret:
        _mock_github_webhook_secret.return_value = secret
        yield secret


def test_verify_signature(mock_github_webhook_secret):
    signature = "b611249a28989845434bfbe56cc4ebe0dfeb89161203157f82f43dd97de7eaa9"
    payload = "fe11f072e13fd8deefe7d906e7d59a673f1d7a7d"
    verify_signature(signature, payload)


def test_verify_signature_exception(mock_github_webhook_secret):
    signature = "b611249a28989845434bfbe56cc4ebe0dfeb89161203157f82f43dd97de7eaa9"
    payload = "foo"
    with pytest.raises(Exception):
        verify_signature(signature, payload)
