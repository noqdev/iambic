from __future__ import annotations

import unittest.mock

import pytest
from mock import AsyncMock
from pydantic import SecretStr

from iambic.core.iambic_enum import IambicManaged
from iambic.core.models import Command, ExecutionMessage
from iambic.plugins.v0_1_0.google_workspace.handlers import import_google_resources
from iambic.plugins.v0_1_0.google_workspace.iambic_plugin import (
    GoogleProject,
    GoogleSubject,
    GoogleWorkspaceConfig,
)


@pytest.mark.asyncio
async def test_import_google_resources():
    # Mock ExecutionMessage
    exe_message = ExecutionMessage(
        execution_id="11928f24-11f4-4629-a38f-9c24c5551e89",
        command=Command.IMPORT,
        parent_command=Command.IMPORT,
        provider_type=None,
        provider_id=None,
        template_type=None,
        template_id=None,
        metadata=None,
        templates=None,
    )

    # Mock GoogleWorkspaceConfig
    config = GoogleWorkspaceConfig(
        workspaces=[
            GoogleProject(
                project_id="example-ga",
                project_name=None,
                subjects=[
                    GoogleSubject(
                        domain="example.com",
                        service_account="google-groups-test@example-ga.iam.gserviceaccount.com",
                    )
                ],
                type="service_account",
                private_key_id="12345",
                private_key=SecretStr("**********"),
                client_email="google-groups-test@example-ga.iam.gserviceaccount.com",
                client_id="12345",
                auth_uri="https://accounts.google.com/o/oauth2/auth",
                token_uri="https://oauth2.googleapis.com/token",
                auth_provider_x509_cert_url="https://www.googleapis.com/oauth2/v1/certs",
                client_x509_cert_url="https://www.googleapis.com/robot/v1/metadata/x509/google-groups-test%40example-ga.iam.gserviceaccount.com",
                variables=[],
                iambic_managed=IambicManaged.UNDEFINED,
            )
        ]
    )
    base_output_dir = "../example-templates-local"
    messages = None
    remote_worker = None

    # Mock the collect_project_groups and generate_group_templates functions
    with unittest.mock.patch(
        "iambic.plugins.v0_1_0.google_workspace.handlers.collect_project_groups",
        new_callable=AsyncMock,
    ) as mock_collect_project_groups, unittest.mock.patch(
        "iambic.plugins.v0_1_0.google_workspace.handlers.generate_group_templates",
        new_callable=AsyncMock,
    ) as mock_generate_group_templates:
        # Call the import_google_resources function
        await import_google_resources(
            exe_message, config, base_output_dir, messages, remote_worker
        )

        # Assert that the mocked functions were called with the expected arguments
        mock_collect_project_groups.assert_called()
        mock_generate_group_templates.assert_called_with(
            exe_message, config, base_output_dir
        )
