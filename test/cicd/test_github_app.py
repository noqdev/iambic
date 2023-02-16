from __future__ import annotations

import pytest

import iambic.cicd.github_app
from iambic.cicd.github_app import calculate_signature, verify_signature


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
    old_value = iambic.cicd.github_app.__GITHUB_APP_WEBHOOK_SECRET__
    secret = "e9aec442806878a2ab7bc0676c515e03c1a8ab59"
    iambic.cicd.github_app.__GITHUB_APP_WEBHOOK_SECRET__ = secret
    yield secret
    iambic.cicd.github_app.__GITHUB_APP_WEBHOOK_SECRET__ = old_value


def test_verify_signature(mock_github_webhook_secret):
    signature = "b611249a28989845434bfbe56cc4ebe0dfeb89161203157f82f43dd97de7eaa9"
    payload = "fe11f072e13fd8deefe7d906e7d59a673f1d7a7d"
    verify_signature(signature, payload)
