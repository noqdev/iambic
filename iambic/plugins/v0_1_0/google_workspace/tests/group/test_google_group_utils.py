from __future__ import annotations

import unittest
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock

from iambic.core.models import ProposedChange, ProposedChangeType
from iambic.plugins.v0_1_0.google_workspace.group.models import (
    GoogleWorkspaceGroupTemplate,
    GroupMember,
    GroupProperties,
)
from iambic.plugins.v0_1_0.google_workspace.group.utils import (
    create_group,
    list_groups,
    maybe_delete_group,
    update_group_description,
    update_group_domain,
    update_group_email,
    update_group_members,
    update_group_name,
)
from iambic.plugins.v0_1_0.google_workspace.iambic_plugin import GoogleProject
from iambic.plugins.v0_1_0.google_workspace.models import (
    GroupMemberRole,
    GroupMemberStatus,
    GroupMemberType,
)


class TestListGroups(IsolatedAsyncioTestCase):
    async def test_list_groups(self):
        # Set up mock data
        domain = "example.com"
        group_data = [
            {"id": "group1@example.com", "email": "group1@example.com"},
            {"id": "group2@example.com", "email": "group2@example.com"},
        ]

        # Set up mock service connection
        mock_service = MagicMock()
        mock_service.groups.return_value.list.return_value.execute.return_value = {
            "groups": group_data,
        }
        google_project = MagicMock()
        google_project.get_service_connection = AsyncMock(return_value=mock_service)

        # Set up mock get_group_template function

        with unittest.mock.patch(
            "iambic.plugins.v0_1_0.google_workspace.group.models.get_group_template",
            new_callable=AsyncMock,
        ) as mock_get_group_template:
            mock_get_group_template.side_effect = lambda service, group, domain: group

            # Call list_groups function
            result = await list_groups(domain, google_project)

            # Check if the result is as expected
            self.assertEqual(len(result), len(group_data))
            for idx, group in enumerate(result):
                self.assertEqual(group["id"], group_data[idx]["id"])
                self.assertEqual(group["email"], group_data[idx]["email"])

            # Check if the get_group_template function was called for each group
            self.assertEqual(mock_get_group_template.call_count, len(group_data))


class TestCreateGroup(IsolatedAsyncioTestCase):
    async def test_create_group(self):
        # Set up mock data
        domain = "example.com"
        group_id = "group1@example.com"
        group_email = "group1@example.com"
        group_name = "Group 1"
        group_description = "A test group"

        # Set up mock service connection
        mock_service = MagicMock()
        mock_service.groups.return_value.insert.return_value.execute.return_value = {
            "id": group_id,
            "email": group_email,
            "name": group_name,
            "description": group_description,
        }
        google_project = MagicMock()
        google_project.get_service_connection = AsyncMock(return_value=mock_service)

        # Call create_group function
        result = await create_group(
            id=group_id,
            domain=domain,
            email=group_email,
            name=group_name,
            description=group_description,
            google_project=google_project,
        )

        # Check if the result is as expected
        self.assertEqual(result["id"], group_id)
        self.assertEqual(result["email"], group_email)
        self.assertEqual(result["name"], group_name)
        self.assertEqual(result["description"], group_description)

        # Check if the insert function was called with the correct parameters
        mock_service.groups.return_value.insert.assert_called_with(
            body={
                "id": group_id,
                "email": group_email,
                "name": group_name,
                "description": group_description,
            }
        )


class TestUpdateGroupDomain(IsolatedAsyncioTestCase):
    async def test_update_group_domain_same_domain(self):
        current_domain = "example.com"
        proposed_domain = "example.com"
        log_params = {
            "resource_type": "google:group",
            "resource_id": "group1@example.com",
            "account": "example.com",
        }

        result = await update_group_domain(current_domain, proposed_domain, log_params)

        self.assertEqual(result, [])

    async def test_update_group_domain_different_domain(self):
        current_domain = "example.com"
        proposed_domain = "newexample.com"
        log_params = {
            "resource_type": "google:group",
            "resource_id": "group1@example.com",
            "account": "example.com",
        }
        with self.assertRaises(NotImplementedError):
            await update_group_domain(current_domain, proposed_domain, log_params)


class TestUpdateGroupDescription(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.google_project = MagicMock(spec=GoogleProject)
        self.google_project.get_service_connection = AsyncMock(return_value=MagicMock())
        self.log_params = {
            "resource_type": "google:group",
            "resource_id": "group1@example.com",
            "account": "example.com",
        }

    async def test_update_group_description_same_description(self):
        group_email = "group1@example.com"
        current_description = "Current Group Description"
        proposed_description = "Current Group Description"
        domain = "example.com"

        result = await update_group_description(
            group_email,
            current_description,
            proposed_description,
            domain,
            self.google_project,
            self.log_params,
        )

        self.assertEqual(result, [])

    async def test_update_group_description_different_description(self):
        group_email = "group1@example.com"
        current_description = "Current Group Description"
        proposed_description = "New Group Description"
        domain = "example.com"

        result = await update_group_description(
            group_email,
            current_description,
            proposed_description,
            domain,
            self.google_project,
            self.log_params,
        )

        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], ProposedChange)
        self.assertEqual(result[0].change_type, ProposedChangeType.UPDATE)
        self.assertEqual(result[0].attribute, "description")
        self.assertEqual(
            result[0].change_summary,
            {
                "current_description": current_description,
                "proposed_description": proposed_description,
            },
        )


class TestUpdateGroupName(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.google_project = MagicMock(spec=GoogleProject)
        self.google_project.get_service_connection = AsyncMock(return_value=MagicMock())
        self.log_params = {
            "resource_type": "google:group",
            "resource_id": "group1@example.com",
            "account": "example.com",
        }

    async def test_update_group_name_same_name(self):
        group_email = "group1@example.com"
        current_name = "Current Group Name"
        proposed_name = "Current Group Name"
        domain = "example.com"

        result = await update_group_name(
            group_email,
            current_name,
            proposed_name,
            domain,
            self.google_project,
            self.log_params,
        )

        self.assertEqual(result, [])

    async def test_update_group_name_different_name(self):
        group_email = "group1@example.com"
        current_name = "Current Group Name"
        proposed_name = "New Group Name"
        domain = "example.com"

        result = await update_group_name(
            group_email,
            current_name,
            proposed_name,
            domain,
            self.google_project,
            self.log_params,
        )

        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], ProposedChange)
        self.assertEqual(result[0].change_type, ProposedChangeType.UPDATE)
        self.assertEqual(result[0].attribute, "group_name")
        self.assertEqual(result[0].new_value, proposed_name)


class TestUpdateGroupEmail(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.google_project = MagicMock(spec=GoogleProject)
        self.google_project.get_service_connection = AsyncMock(return_value=MagicMock())
        self.log_params = {
            "resource_type": "google:group",
            "resource_id": "group1@example.com",
            "account": "example.com",
        }

    async def test_update_group_email_same_email(self):
        current_email = "group1@example.com"
        proposed_email = "group1@example.com"
        domain = "example.com"

        result = await update_group_email(
            current_email,
            proposed_email,
            domain,
            self.google_project,
            self.log_params,
        )

        self.assertEqual(result, [])

    async def test_update_group_email_different_email(self):
        current_email = "group1@example.com"
        proposed_email = "group2@example.com"
        domain = "example.com"

        result = await update_group_email(
            current_email,
            proposed_email,
            domain,
            self.google_project,
            self.log_params,
        )

        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], ProposedChange)
        self.assertEqual(result[0].change_type, ProposedChangeType.UPDATE)
        self.assertEqual(result[0].attribute, "group_email")
        self.assertEqual(result[0].new_value, proposed_email)


class TestMaybeDeleteGroup(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.google_project = MagicMock(spec=GoogleProject)
        self.google_project.get_service_connection = AsyncMock(return_value=MagicMock())
        self.log_params = {
            "resource_type": "google:group",
            "resource_id": "group1@example.com",
            "account": "example.com",
        }

    async def test_maybe_delete_group_not_deleted(self):
        group = GoogleWorkspaceGroupTemplate(
            properties=GroupProperties(
                email="group1@example.com",
                name="Group 1",
                domain="example.com",
                description="test_group",
                members=[],
            ),
            deleted=False,
            file_path="test_google_group.yaml",
        )

        result = await maybe_delete_group(
            group,
            self.google_project,
            self.log_params,
        )

        self.assertEqual(result, [])

    async def test_maybe_delete_group_deleted(self):
        group = GoogleWorkspaceGroupTemplate(
            file_path="test_google_group.yaml",
            properties=GroupProperties(
                email="group1@example.com",
                name="Group 1",
                domain="example.com",
                description="test_group",
                members=[],
            ),
            deleted=True,
        )
        result = await maybe_delete_group(
            group,
            self.google_project,
            self.log_params,
        )

        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], ProposedChange)
        self.assertEqual(result[0].change_type, ProposedChangeType.DELETE)
        self.assertEqual(result[0].attribute, "group")
        self.assertEqual(result[0].change_summary, {"group": group.properties.name})


class TestUpdateGroupMembers(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.google_project = MagicMock(spec=GoogleProject)
        self.google_project.get_service_connection = AsyncMock(return_value=MagicMock())
        self.log_params = {
            "resource_type": "google:group",
            "resource_id": "group1@example.com",
            "account": "example.com",
        }

    async def test_update_group_members_no_changes(self):
        group_email = "group1@example.com"
        current_members = [
            GroupMember(
                email="user1@example.com",
                role=GroupMemberRole.MEMBER,
                type=GroupMemberType.USER,
                status=GroupMemberStatus.ACTIVE,
            ),
        ]
        proposed_members = current_members

        result = await update_group_members(
            group_email,
            current_members,
            proposed_members,
            "example.com",
            self.google_project,
            self.log_params,
        )

        self.assertEqual(result, [])

    async def test_update_group_members_add_and_remove(self):
        group_email = "group1@example.com"
        current_members = [
            GroupMember(
                email="user1@example.com",
                role=GroupMemberRole.MEMBER,
                type=GroupMemberType.USER,
                status=GroupMemberStatus.ACTIVE,
            ),
        ]
        proposed_members = [
            GroupMember(
                email="user2@example.com",
                role=GroupMemberRole.MEMBER,
                type=GroupMemberType.USER,
                status=GroupMemberStatus.ACTIVE,
            ),
        ]

        result = await update_group_members(
            group_email,
            current_members,
            proposed_members,
            "example.com",
            self.google_project,
            self.log_params,
        )

        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], ProposedChange)
        self.assertEqual(result[0].change_type, ProposedChangeType.DETACH)
        self.assertEqual(result[0].attribute, "users")
        self.assertEqual(
            result[0].change_summary, {"UsersToRemove": ["user1@example.com"]}
        )

        self.assertIsInstance(result[1], ProposedChange)
        self.assertEqual(result[1].change_type, ProposedChangeType.ATTACH)
        self.assertEqual(result[1].attribute, "users")
        self.assertEqual(
            result[1].change_summary, {"UsersToAdd": ["user2@example.com"]}
        )
