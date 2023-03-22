from __future__ import annotations

import pytest
from googleapiclient.errors import UnknownApiNameOrVersion
from mock import MagicMock, patch

from iambic.plugins.v0_1_0.google_workspace.iambic_plugin import (
    GoogleProject,
    GoogleSubject,
    SecretStr,
)


@pytest.fixture
def google_project():
    return GoogleProject(
        project_id="example-ga",
        project_name=None,
        subjects=[
            GoogleSubject(
                domain="example.com",
                service_account="google-groups-test@example.iam.gserviceaccount.com",
            )
        ],
        type="service_account",
        private_key_id="123456",
        private_key=SecretStr("**********"),
        client_email="google-groups-test@example.iam.gserviceaccount.com",
        client_id="123456",
        auth_uri="https://accounts.google.com/o/oauth2/auth",
        token_uri="https://oauth2.googleapis.com/token",
        auth_provider_x509_cert_url="https://www.googleapis.com/oauth2/v1/certs",
        client_x509_cert_url="https://www.googleapis.com/robot/v1/metadata/x509/google-groups-test%40example-ga.iam.gserviceaccount.com",
        variables=[],
        iambic_managed=None,
    )


def test_google_project_str(google_project):
    assert str(google_project) == "example-ga"


@pytest.mark.asyncio
@patch("google.oauth2.service_account.Credentials.from_service_account_info")
async def test_google_project_get_service_connection(
    mock_from_service_account_info, google_project
):
    mock_credentials = MagicMock()
    mock_from_service_account_info.return_value = mock_credentials

    service_conn = await google_project.get_service_connection(
        service_name="admin",
        service_path="directory_v1",
        domain="example.com",
        cache_discovery=False,
    )

    assert service_conn is not None
    mock_from_service_account_info.assert_called_once()


@pytest.mark.asyncio
@patch("google.oauth2.service_account.Credentials.from_service_account_info")
async def test_google_project_get_service_connection_no_subject(
    mock_from_service_account_info, google_project
):
    mock_credentials = MagicMock()
    mock_from_service_account_info.return_value = mock_credentials

    with pytest.raises(
        Exception,
        match=r"Could not find service account for domain non_existent_domain",
    ):
        await google_project.get_service_connection(
            service_name="admin",
            service_path="directory_v1",
            domain="non_existent_domain",
            cache_discovery=False,
        )


@pytest.mark.asyncio
@patch("google.oauth2.service_account.Credentials.from_service_account_info")
async def test_google_project_get_service_connection_unknown_api(
    mock_from_service_account_info, google_project
):
    mock_credentials = MagicMock()
    mock_from_service_account_info.return_value = mock_credentials

    with pytest.raises(UnknownApiNameOrVersion):
        await google_project.get_service_connection(
            service_name="non_existent_service",
            service_path="non_existent_service_v1",
            domain="example.com",
            cache_discovery=False,
        )
