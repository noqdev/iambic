from __future__ import annotations

import asyncio
import datetime
import uuid

from functional_tests.azure_ad.base_test_case import BaseMS365TestCase
from functional_tests.azure_ad.group.utils import generate_group_template
from functional_tests.conftest import IAMBIC_TEST_DETAILS
from iambic.core.context import ctx
from iambic.core.iambic_enum import Command
from iambic.core.models import ExecutionMessage
from iambic.core.parser import load_templates
from iambic.plugins.v0_1_0.azure_ad.group.models import Member, MemberDataType
from iambic.plugins.v0_1_0.azure_ad.group.utils import get_group
from iambic.request_handler.expire_resources import flag_expired_resources


class UpdateMS365GroupTestCase(BaseMS365TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.template = generate_group_template()
        cls.group_name = cls.template.properties.name
        cls.org = IAMBIC_TEST_DETAILS.config.azure_ad.organizations[0]
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config.azure_ad, ctx))

    @classmethod
    def tearDownClass(cls):
        cls.template.deleted = True
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config.azure_ad, ctx))

    async def test_update_description(self):
        self.template.properties.description = "Updated description"
        await self.template.apply(IAMBIC_TEST_DETAILS.config.azure_ad, ctx)

        try:
            group = await get_group(self.org, group_name=self.group_name)
        except Exception as err:
            self.fail(f"Unable to retrieve Group: {err}")

        self.assertEqual(
            self.template.properties.description,
            group.description,
            "Description was not updated",
        )

    async def test_add_user_member(self):
        existing_member_ids = [member.id for member in self.template.properties.members]
        new_member = self.get_random_user(excluded_user_ids=existing_member_ids)
        self.template.properties.members = [
            Member(
                id=new_member.user_id,
                name=new_member.username,
                data_type=MemberDataType.USER,
            )
        ]
        await self.template.apply(IAMBIC_TEST_DETAILS.config.azure_ad, ctx)

        try:
            group = await get_group(self.org, group_name=self.group_name)
        except Exception as err:
            self.fail(f"Unable to retrieve Group: {err}")

        group_members = [member.name for member in group.members]
        self.assertIn(new_member.username, group_members)

    async def test_remove_user_member(self):
        existing_member_ids = [member.id for member in self.template.properties.members]
        user_member = self.get_random_user(excluded_user_ids=existing_member_ids)
        self.template.properties.members = [
            Member(
                id=user_member.user_id,
                name=user_member.username,
                data_type=MemberDataType.USER,
            )
        ]
        await self.template.apply(IAMBIC_TEST_DETAILS.config.azure_ad, ctx)

        self.template.properties.members = [
            member
            for member in self.template.properties.members
            if member.id != user_member.user_id
        ]
        await self.template.apply(IAMBIC_TEST_DETAILS.config.azure_ad, ctx)

        try:
            group = await get_group(self.org, group_name=self.group_name)
        except Exception as err:
            self.fail(f"Unable to retrieve Group: {err}")

        group_members = [member.name for member in group.members]
        self.assertNotIn(user_member.username, group_members)

    async def test_expire_member(self):
        existing_member_ids = [member.id for member in self.template.properties.members]
        user_member = self.get_random_user(excluded_user_ids=existing_member_ids)
        existing_member_ids.append(user_member.user_id)
        user_member_2 = self.get_random_user(excluded_user_ids=existing_member_ids)

        self.template.properties.members = [
            Member(
                id=user_member.user_id,
                name=user_member.username,
                data_type=MemberDataType.USER,
            ),
            Member(
                id=user_member_2.user_id,
                name=user_member_2.username,
                data_type=MemberDataType.USER,
            ),
        ]
        await self.template.apply(IAMBIC_TEST_DETAILS.config.azure_ad, ctx)

        expired_member = self.template.properties.members[0].name
        cur_time = datetime.datetime.now(datetime.timezone.utc)
        exe_message = ExecutionMessage(
            execution_id=str(uuid.uuid4()), command=Command.APPLY
        )
        self.template.properties.members[0].expires_at = cur_time - datetime.timedelta(
            days=1
        )

        unexpired_member = self.template.properties.members[1].name
        self.template.properties.members[1].expires_at = cur_time + datetime.timedelta(
            days=1
        )

        # Write new template, apply, and confirm access removed
        await flag_expired_resources([self.template.file_path])
        await IAMBIC_TEST_DETAILS.config.run_apply(exe_message, [self.template])

        group = load_templates([self.template.file_path])[0]
        group_members = [member.name for member in group.properties.members]
        self.assertIn(unexpired_member, group_members)
        self.assertNotIn(expired_member, group_members)


class UpdateSecurityGroupTestCase(BaseMS365TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.template = generate_group_template()
        cls.template.properties.security_enabled = True
        cls.template.properties.mail_enabled = False
        cls.template.properties.members = []
        cls.template.properties.group_types = []
        cls.template.write(exclude_unset=False)
        cls.group_name = cls.template.properties.name
        cls.org = IAMBIC_TEST_DETAILS.config.azure_ad.organizations[0]
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config.azure_ad, ctx))

    @classmethod
    def tearDownClass(cls):
        cls.template.deleted = True
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config.azure_ad, ctx))

    async def test_update_description(self):
        self.template.properties.description = "Updated description"
        await self.template.apply(IAMBIC_TEST_DETAILS.config.azure_ad, ctx)

        try:
            group = await get_group(self.org, group_name=self.group_name)
        except Exception as err:
            self.fail(f"Unable to retrieve Group: {err}")

        self.assertEqual(
            self.template.properties.description,
            group.description,
            "Description was not updated",
        )

    async def test_add_group_member(self):
        new_member = self.get_random_group(
            excluded_group_ids=[self.template.properties.group_id]
        )
        self.template.properties.members = [
            Member(
                id=new_member.group_id,
                name=new_member.resource_id,
                data_type=MemberDataType.GROUP,
            )
        ]
        await self.template.apply(IAMBIC_TEST_DETAILS.config.azure_ad, ctx)

        try:
            group = await get_group(self.org, group_name=self.group_name)
        except Exception as err:
            self.fail(f"Unable to retrieve Group: {err}")

        group_members = [member.name for member in group.members]
        self.assertIn(new_member.resource_id, group_members)

    async def test_add_user_and_group_members(self):
        existing_member_ids = [member.id for member in self.template.properties.members]
        existing_member_ids.append(self.template.properties.group_id)
        new_group_member = self.get_random_group(excluded_group_ids=existing_member_ids)
        new_user_member = self.get_random_user(excluded_user_ids=existing_member_ids)
        self.template.properties.members = [
            Member(
                id=new_user_member.user_id,
                name=new_user_member.username,
                data_type=MemberDataType.USER,
            ),
            Member(
                id=new_group_member.group_id,
                name=new_group_member.resource_id,
                data_type=MemberDataType.GROUP,
            ),
        ]
        await self.template.apply(IAMBIC_TEST_DETAILS.config.azure_ad, ctx)

        try:
            group = await get_group(self.org, group_name=self.group_name)
        except Exception as err:
            self.fail(f"Unable to retrieve Group: {err}")

        group_members = [member.name for member in group.members]
        self.assertIn(new_group_member.resource_id, group_members)
        self.assertIn(new_user_member.username, group_members)

    async def test_remove_user_and_group_members(self):
        existing_member_ids = [member.id for member in self.template.properties.members]
        existing_member_ids.append(self.template.properties.group_id)
        group_member = self.get_random_group(excluded_group_ids=existing_member_ids)
        user_member = self.get_random_user(excluded_user_ids=existing_member_ids)
        self.template.properties.members = [
            Member(
                id=user_member.user_id,
                name=user_member.username,
                data_type=MemberDataType.USER,
            ),
            Member(
                id=group_member.group_id,
                name=group_member.resource_id,
                data_type=MemberDataType.GROUP,
            ),
        ]
        await self.template.apply(IAMBIC_TEST_DETAILS.config.azure_ad, ctx)

        self.template.properties.members = [
            member
            for member in self.template.properties.members
            if member.id not in [user_member.user_id, group_member.group_id]
        ]
        await self.template.apply(IAMBIC_TEST_DETAILS.config.azure_ad, ctx)

        try:
            group = await get_group(self.org, group_name=self.group_name)
        except Exception as err:
            self.fail(f"Unable to retrieve Group: {err}")

        group_members = [member.name for member in group.members]
        self.assertNotIn(group_member.resource_id, group_members)
        self.assertNotIn(user_member.username, group_members)
