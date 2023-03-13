from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from iambic.plugins.v0_1_0.github.github_app import (
    _get_installation_token,
    calculate_signature,
    run_handler,
    verify_signature,
)


@pytest.fixture()
def mock_pull_request_webhook_lambda_event():
    return {
        "headers": {
            "x-github-event": "pull_request",
            "x-github-hook-installation-target-id": "fake_app_id",
            "x-hub-signature-256": "sha256=fake-signature",
        },
        "body": json.dumps({"installation": {"id": "fake-installation-id"}}),
    }


@pytest.fixture()
def mock_unknown_webhook_lambda_event():
    return {
        "headers": {
            "x-github-event": "unknown",
            "x-github-hook-installation-target-id": "fake_app_id",
            "x-hub-signature-256": "sha256=fake-signature",
        },
        "body": json.dumps({"installation": {"id": "fake-installation-id"}}),
    }


@pytest.fixture()
def skip_signature_verification():
    with patch(
        "iambic.plugins.v0_1_0.github.github_app.verify_signature",
        autospec=True,
    ) as _:
        yield _


@pytest.fixture()
def skip_installation_token():
    with patch(
        "iambic.plugins.v0_1_0.github.github_app._get_installation_token",
        autospec=True,
    ):
        with patch(
            "iambic.plugins.v0_1_0.github.github_app.get_app_private_key_as_lambda_context",
            autospec=True,
        ):
            with patch(
                "iambic.plugins.v0_1_0.github.github_app.get_app_bearer_token",
                autospec=True,
            ) as _:
                yield _


@pytest.fixture()
def mock_github_cls():
    with patch(
        "github.Github",
        autospec=True,
    ) as _:
        yield _


@pytest.fixture()
def skip_authentication(skip_signature_verification, skip_installation_token):
    yield


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
    with pytest.raises(Exception) as excinfo:
        verify_signature(signature, payload)
        assert "Bad signature" in excinfo


def test_run_handler_with_bad_signature(mock_pull_request_webhook_lambda_event):
    with pytest.raises(Exception):
        run_handler(mock_pull_request_webhook_lambda_event, None)


def test_run_handler_with_unknown_event(
    skip_authentication, mock_github_cls, mock_unknown_webhook_lambda_event
):

    from iambic.plugins.v0_1_0.github.github_app import iambic_app

    output_path_before_lambda_call = getattr(iambic_app, "lambda").app.PLAN_OUTPUT_PATH
    repo_base_path_before_lambda_call = getattr(iambic_app, "lambda").app.REPO_BASE_PATH

    import iambic.plugins.v0_1_0.github.github

    data_path_before_lambda_call = (
        iambic.plugins.v0_1_0.github.github.SHARED_CONTAINER_GITHUB_DIRECTORY
    )

    import iambic.core.utils

    writable_directory_before_lambda_call = iambic.core.utils.get_writable_directory()

    with pytest.raises(Exception) as excinfo:
        run_handler(mock_unknown_webhook_lambda_event, None)
        assert "no supported handler" in excinfo.value

        # verify during lambda call, filesystem path are updated
        output_path_after_lambda_call = getattr(
            iambic_app, "lambda"
        ).app.PLAN_OUTPUT_PATH
        repo_base_path_after_lambda_call = getattr(
            iambic_app, "lambda"
        ).app.REPO_BASE_PATH
        assert output_path_before_lambda_call != output_path_after_lambda_call
        assert repo_base_path_before_lambda_call != repo_base_path_after_lambda_call
        data_path_after_lambda_call = (
            iambic.plugins.v0_1_0.github.github.SHARED_CONTAINER_GITHUB_DIRECTORY
        )
        assert data_path_before_lambda_call != data_path_after_lambda_call
        writable_directory_after_lambda_call = (
            iambic.core.utils.get_writable_directory()
        )
        assert (
            writable_directory_before_lambda_call
            != writable_directory_after_lambda_call
        )


class MockResponse:
    def __init__(self, text, status):
        self._text = text
        self.status = status

    async def text(self):
        return self._text

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def __aenter__(self):
        return self


@pytest.mark.asyncio
async def test_get_installation_token(skip_authentication):
    data = {"token": "fake_token"}
    resp = MockResponse(json.dumps(data), 200)

    with patch("aiohttp.ClientSession.post", return_value=resp):
        token = await _get_installation_token("fake_app_id", "fake_installation_id")
        assert token == "fake_token"
