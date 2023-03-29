from __future__ import annotations

import os
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from pydantic import SecretStr

from iambic.core.iambic_enum import IambicManaged
from iambic.core.models import ExecutionMessage
from iambic.plugins.v0_1_0.google_workspace.group.models import (
    GoogleWorkspaceGroupTemplate,
)
from iambic.plugins.v0_1_0.google_workspace.group.template_generation import (
    collect_project_groups,
    generate_domain_group_resource_files,
    generate_group_templates,
    get_group_dir,
    get_resource_dir_args,
    get_response_dir,
    get_templated_resource_file_path,
    update_or_create_group_template,
)
from iambic.plugins.v0_1_0.google_workspace.iambic_plugin import (
    GoogleProject,
    GoogleSubject,
    GoogleWorkspaceConfig,
)


class TestGenerateGroupTemplates(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.exe_message = MagicMock(spec=ExecutionMessage)
        self.exe_message.get_sub_exe_files = AsyncMock(return_value=[])
        self.config = GoogleWorkspaceConfig(
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
        self.output_dir = "test_output"

    @patch(
        "iambic.plugins.v0_1_0.google_workspace.group.template_generation.get_existing_template_map",
        return_value={},
    )
    @patch(
        "iambic.plugins.v0_1_0.google_workspace.group.template_generation.update_or_create_group_template"
    )
    @patch(
        "iambic.plugins.v0_1_0.google_workspace.group.template_generation.delete_orphaned_templates"
    )
    async def test_generate_group_templates_no_groups(
        self,
        mock_delete_orphaned_templates,
        mock_update_or_create_group_template,
        mock_get_existing_template_map,
    ):
        await generate_group_templates(
            self.exe_message,
            self.config,
            self.output_dir,
        )

        self.exe_message.get_sub_exe_files.assert_called_once()
        mock_get_existing_template_map.assert_called_once()
        mock_update_or_create_group_template.assert_not_called()
        mock_delete_orphaned_templates.assert_called_once_with([], set())

    async def test_generate_group_templates_with_groups(self):
        groups = [
            {
                "properties": {
                    "name": "Group 1",
                    "email": "group1@example.com",
                    "description": "Group 1 description",
                    "domain": "example.com",
                    "members": [],
                },
            },
        ]

        group_template = GoogleWorkspaceGroupTemplate(
            **groups[0], file_path="test_path.yaml"
        )

        self.exe_message.get_sub_exe_files = AsyncMock(return_value=groups)

        with patch(
            "iambic.plugins.v0_1_0.google_workspace.group.template_generation.get_existing_template_map",
            return_value={},
        ), patch(
            "iambic.plugins.v0_1_0.google_workspace.group.template_generation.update_or_create_group_template"
        ) as mock_update_or_create_group_template, patch(
            "iambic.plugins.v0_1_0.google_workspace.group.template_generation.delete_orphaned_templates"
        ) as mock_delete_orphaned_templates:
            mock_update_or_create_group_template.return_value = group_template
            await generate_group_templates(
                self.exe_message,
                self.config,
                self.output_dir,
            )

            self.exe_message.get_sub_exe_files.assert_called_once()
            mock_update_or_create_group_template.assert_called_once()
            mock_delete_orphaned_templates.assert_called_once_with(
                [], {"group1@example.com"}
            )


class TestTemplateGenerationFunctions(IsolatedAsyncioTestCase):
    def test_get_resource_dir_args(self):
        domain = "example.com"
        expected_args = ["group", "example.com"]
        self.assertEqual(get_resource_dir_args(domain), expected_args)

    def test_get_response_dir(self):
        exe_message = ExecutionMessage(
            provider_id="test_provider_id",
            execution_id="test_execution_id",
            command="import",
        )
        # exe_message.get_directory.return_value = "test_directory"
        google_project = MagicMock(spec=GoogleProject)
        google_project.project_id = "test_project_id"
        domain = "example.com"

        expected_dir = "test_provider_id/group/example.com/templates"

        assert get_response_dir(exe_message, google_project, domain).endswith(
            expected_dir
        )

    def test_get_group_dir(self):
        base_dir = "test_base_dir"
        domain = "example.com"
        expected_path = os.path.join(
            "test_base_dir",
            "resources",
            "google_workspace",
            "group",
            "example.com",
        )
        self.assertEqual(get_group_dir(base_dir, domain), expected_path)

    def test_get_templated_resource_file_path(self):
        resource_dir = "test_resource_dir"
        resource_email = "test_group@example.com"
        expected_path = os.path.join("test_resource_dir", "test_group.yaml")
        self.assertEqual(
            get_templated_resource_file_path(resource_dir, resource_email),
            expected_path,
        )

    @patch(
        "iambic.plugins.v0_1_0.google_workspace.group.template_generation.list_groups"
    )
    @patch(
        "iambic.plugins.v0_1_0.google_workspace.group.template_generation.GoogleWorkspaceGroupTemplate.write"
    )
    async def test_generate_domain_group_resource_files(
        self, mock_group_write, mock_list_groups
    ):
        exe_message = ExecutionMessage(
            provider_id="test_provider_id",
            execution_id="test_execution_id",
            command="import",
        )
        project = MagicMock(spec=GoogleProject)
        project.project_id = "test_project_id"
        domain = "example.com"

        group = GoogleWorkspaceGroupTemplate(
            file_path="unset",
            properties={
                "name": "Group 1",
                "email": "group1@example.com",
                "description": "Group 1 description",
                "members": [],
                "domain": "example.com",
            },
        )
        mock_list_groups.return_value = [group]

        await generate_domain_group_resource_files(exe_message, project, domain)

        mock_list_groups.assert_called_once_with(domain, project)
        mock_group_write.assert_called_once()

    async def test_update_or_create_group_template(self):
        existing_template_map = {}
        group_dir = "test_group_dir"
        discovered_group_template = GoogleWorkspaceGroupTemplate(
            file_path="unset",
            properties={
                "name": "Group 1",
                "email": "group1@example.com",
                "description": "Group 1 description",
                "members": [],
                "domain": "example.com",
            },
        )

        with patch(
            "iambic.plugins.v0_1_0.google_workspace.group.template_generation.common_create_or_update_template"
        ) as mock_common_create_or_update_template:
            mock_common_create_or_update_template.return_value = (
                discovered_group_template
            )

            result = await update_or_create_group_template(
                discovered_group_template, existing_template_map, group_dir
            )

            mock_common_create_or_update_template.assert_called_once_with(
                discovered_group_template.file_path,
                existing_template_map,
                discovered_group_template.resource_id,
                GoogleWorkspaceGroupTemplate,
                {},
                discovered_group_template.properties,
                [],
            )
            self.assertEqual(result, discovered_group_template)

    @patch(
        "iambic.plugins.v0_1_0.google_workspace.group.template_generation.generate_domain_group_resource_files"
    )
    async def test_collect_project_groups(
        self, mock_generate_domain_group_resource_files
    ):
        exe_message = ExecutionMessage(
            provider_id="test_provider_id",
            execution_id="test_execution_id",
            command="import",
        )
        exe_message.provider_id = "test_project_id"
        project = MagicMock(spec=GoogleProject)
        project.project_id = "test_project_id"
        subject = GoogleSubject(
            domain="example.com",
            service_account="google-groups-test@example-ga.iam.gserviceaccount.com",
        )
        config = GoogleWorkspaceConfig(
            workspaces=[
                GoogleProject(
                    project_id="example-ga",
                    project_name=None,
                    subjects=[subject],
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
        with self.assertRaises(Exception):
            await collect_project_groups(exe_message, config)

        mock_generate_domain_group_resource_files.assert_not_called()
        mock_generate_domain_group_resource_files.reset_mock()
        project.project_id = "example-ga"
        exe_message.provider_id = "example-ga"
        await collect_project_groups(exe_message, config)
        mock_generate_domain_group_resource_files.assert_called_once()
