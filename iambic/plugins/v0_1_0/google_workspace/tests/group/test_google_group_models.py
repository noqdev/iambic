from __future__ import annotations

import copy
import os
import tempfile
import unittest

from mock import AsyncMock, MagicMock

from iambic.core.context import ctx
from iambic.core.models import ProposedChangeType, TemplateChangeDetails
from iambic.plugins.v0_1_0.google_workspace.iambic_plugin import (
    GoogleProject,
    GoogleWorkspaceConfig,
)


class TestGroupTemplateApply(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from iambic.plugins.v0_1_0.google_workspace.group.models import (
            GoogleWorkspaceGroupTemplate,
            GroupMember,
            GroupProperties,
        )

        workspaces = []
        self.google_workspace_config = GoogleWorkspaceConfig(workspaces=workspaces)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.temp_file_path = os.path.join(self.temp_dir.name, "test_path.yaml")
        self.template = GoogleWorkspaceGroupTemplate(
            template_type="google:group",
            file_path=self.temp_file_path,
            properties=GroupProperties(
                name="test_group",
                domain="example.com",
                email="test@example.com",
                description="test_description",
                members=[GroupMember(email="testuser@example.com")],
            ),
        )
        self.template_2 = GoogleWorkspaceGroupTemplate(
            template_type="google:group",
            file_path=self.temp_file_path,
            properties=GroupProperties(
                name="test_group",
                domain="example2.com",
                email="test@example2.com",
                description="test_description",
                members=[GroupMember(email="testuser@example2.com")],
            ),
        )

        self.google_project1 = GoogleProject(
            project_id="google_project1",
            subjects=[
                {"domain": "example.com", "service_account": "google_project1_sa"}
            ],
            type="google",
            private_key_id="google_project1_private_key_id",
            private_key="google_project1_private_key",
            client_email="google_project1_client_email",
            client_id="google_project1_client_id",
            auth_uri="google_project1_auth_uri",
            token_uri="google_project1_token_uri",
            auth_provider_x509_cert_url="google_project1_auth_provider_x509_cert_url",
            client_x509_cert_url="google_project1_client_x509_cert_url",
        )
        self.google_project2 = GoogleProject(
            project_id="google_project2",
            subjects=[
                {"domain": "example2.com", "service_account": "google_project2_sa"}
            ],
            type="google",
            private_key_id="google_project2_private_key_id",
            private_key="google_project2_private_key",
            client_email="google_project2_client_email",
            client_id="google_project2_client_id",
            auth_uri="google_project2_auth_uri",
            token_uri="google_project2_token_uri",
            auth_provider_x509_cert_url="google_project2_auth_provider_x509_cert_url",
            client_x509_cert_url="google_project2_client_x509_cert_url",
        )
        mock_req = MagicMock()
        mock_req.execute = MagicMock(
            return_value={
                "name": "test_group",
                "email": "test@example.com",
                "description": "test_description",
            }
        )
        mock_service = MagicMock()
        mock_service.groups.return_value.get.return_value = mock_req
        object.__setattr__(
            self.google_project1,
            "get_service_connection",
            AsyncMock(return_value=mock_service),
        )
        object.__setattr__(
            self.google_project2,
            "get_service_connection",
            AsyncMock(return_value=mock_service),
        )
        self.google_workspace_config.workspaces = [
            self.google_project1,
            self.google_project2,
        ]

    def tearDown(self):
        ctx.eval_only = False

    async def test_apply_with_projects(self):
        ctx.eval_only = True
        google_workspace_config = copy.deepcopy(self.google_workspace_config)
        template_changes = await self.template.apply(google_workspace_config)

        self.assertIsInstance(template_changes, TemplateChangeDetails)
        self.assertEqual(template_changes.resource_id, "test@example.com")
        self.assertEqual(template_changes.resource_type, "google:group")
        self.assertEqual(template_changes.template_path, self.temp_file_path)
        self.assertEqual(len(template_changes.proposed_changes), 1)
        template_changes = await self.template.apply(google_workspace_config)
        self.assertEqual(
            google_workspace_config.workspaces[
                0
            ].get_service_connection.return_value.groups.return_value.get.call_count,
            2,
        )

    async def test_apply_to_account_new_group(self):
        ctx.eval_only = True
        # Set up mock for get_group function to return None (group doesn't exist)
        with unittest.mock.patch(
            "iambic.plugins.v0_1_0.google_workspace.group.models.get_group",
            new_callable=AsyncMock,
        ) as mock_get_group:
            mock_get_group.side_effect = [None, None, self.template]

            # Set up mock for create_group function to simulate group creation
            with unittest.mock.patch(
                "iambic.plugins.v0_1_0.google_workspace.group.models.create_group",
                new_callable=AsyncMock,
            ) as mock_create_group:
                # Call the _apply_to_account method
                change_details = await self.template._apply_to_account(
                    self.google_project1
                )

                # Test that the create_group function not called
                mock_create_group.assert_not_called()

                # Test that the correct changes were proposed
                # Replace with specific assertions based on your implementation
                self.assertEqual(len(change_details.proposed_changes), 1)
                proposed_change = change_details.proposed_changes[0]
                self.assertEqual(proposed_change.change_type, ProposedChangeType.CREATE)
                self.assertEqual(
                    proposed_change.resource_id, self.template.properties.email
                )
                self.assertEqual(
                    proposed_change.resource_type,
                    self.template.properties.resource_type,
                )

                ctx.eval_only = False

                change_details = await self.template._apply_to_account(
                    self.google_project1
                )

                # Test that the create_group function was called
                mock_create_group.assert_called_once_with(
                    id=self.template.properties.email,
                    domain=self.template.properties.domain,
                    email=self.template.properties.email,
                    name=self.template.properties.name,
                    description=self.template.properties.description,
                    google_project=self.google_project1,
                )

                self.assertEqual(len(change_details.proposed_changes), 1)
                proposed_change = change_details.proposed_changes[0]
                self.assertEqual(proposed_change.change_type, ProposedChangeType.CREATE)
                self.assertEqual(
                    proposed_change.resource_id, self.template.properties.email
                )
                self.assertEqual(
                    proposed_change.resource_type,
                    self.template.properties.resource_type,
                )
