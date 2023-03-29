from __future__ import annotations

import pytest

from iambic.plugins.v0_1_0.google_workspace.iambic_plugin import (
    GoogleProject,
    GoogleWorkspaceConfig,
)


def test_google_workspace_config():
    google_project_1 = GoogleProject(
        project_id="fake-project-id",
        type="Group",
        subjects=[{"domain": "example.org", "service_account": "fake-service-account"}],
        private_key_id="fake-private-key-id",
        private_key="fake-private-key",
        client_id="fake-client-id",
        client_email="fake-client-email@example.org",
        auth_uri="https://google.com/",
        token_uri="https://google.com/",
        auth_provider_x509_cert_url="https://google.com/",
        client_x509_cert_url="https://google.com/",
    )

    google_workspace_config = GoogleWorkspaceConfig(workspaces=[google_project_1])
    assert google_workspace_config.workspaces[0].project_id == "fake-project-id"


def test_google_workspace_config_with_repeated_project_id():
    google_project_1 = GoogleProject(
        project_id="fake-project-id",
        type="Group",
        subjects=[{"domain": "example.org", "service_account": "fake-service-account"}],
        private_key_id="fake-private-key-id",
        private_key="fake-private-key",
        client_id="fake-client-id",
        client_email="fake-client-email@example.org",
        auth_uri="https://google.com/",
        token_uri="https://google.com/",
        auth_provider_x509_cert_url="https://google.com/",
        client_x509_cert_url="https://google.com/",
    )

    google_project_2 = GoogleProject(
        project_id="fake-project-id",
        type="Group",
        subjects=[{"domain": "example.org", "service_account": "fake-service-account"}],
        private_key_id="fake-private-key-id",
        private_key="fake-private-key",
        client_id="fake-client-id",
        client_email="fake-client-email@example.org",
        auth_uri="https://google.com/",
        token_uri="https://google.com/",
        auth_provider_x509_cert_url="https://google.com/",
        client_x509_cert_url="https://google.com/",
    )

    with pytest.raises(
        ValueError, match="project_id must be unique within workspaces: fake-project-id"
    ):
        _ = GoogleWorkspaceConfig(workspaces=[google_project_1, google_project_2])
