from __future__ import annotations

import asyncio
import datetime
import uuid
from unittest import IsolatedAsyncioTestCase

from functional_tests.azure_ad.group.utils import generate_group_template
from functional_tests.conftest import IAMBIC_TEST_DETAILS
from iambic.core.context import ctx
from iambic.core.iambic_enum import Command
from iambic.core.models import ExecutionMessage
from iambic.core.parser import load_templates
from iambic.main import run_apply
from iambic.plugins.v0_1_0.azure_ad.group.utils import get_group
from iambic.plugins.v0_1_0.azure_ad.user.models import UserSimple
from iambic.request_handler.expire_resources import flag_expired_resources


class UpdateMS365GroupTestCase(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
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
            "Description was not updated"
        )

    async def test_add_member(self):
        new_member = "matt@noq.dev"
        self.template.properties.members.append(
            UserSimple(
                username=new_member
            )
        )
        await self.template.apply(IAMBIC_TEST_DETAILS.config.azure_ad, ctx)

        try:
            group = await get_group(self.org, group_name=self.group_name)
        except Exception as err:
            self.fail(f"Unable to retrieve Group: {err}")

        group_members = [member.username for member in group.members]
        self.assertIn(new_member, group_members)

    async def test_remove_member(self):
        removed_member = self.template.properties.members.pop(0).username 
        await self.template.apply(IAMBIC_TEST_DETAILS.config.azure_ad, ctx)

        try:
            group = await get_group(self.org, group_name=self.group_name)
        except Exception as err:
            self.fail(f"Unable to retrieve Group: {err}")

        group_members = [member.username for member in group.members]
        self.assertNotIn(removed_member, group_members)

    async def test_expire_member(self):
        expired_member = self.template.properties.members[0].username
        cur_time = datetime.datetime.now(datetime.timezone.utc)
        exe_message = ExecutionMessage(
            execution_id=str(uuid.uuid4()), command=Command.APPLY
        )
        self.template.properties.members[0].expires_at = cur_time - datetime.timedelta(days=1)

        unexpired_member = self.template.properties.members[1].username
        self.template.properties.members[1].expires_at = cur_time + datetime.timedelta(days=1)

        # Write new template, apply, and confirm access removed
        self.template.write()
        await flag_expired_resources([self.template.file_path])
        await IAMBIC_TEST_DETAILS.config.run_apply(exe_message, [self.template])

        group = load_templates([self.template.file_path])[0]
        group_members = [member.username for member in group.properties.members]
        self.assertIn(unexpired_member, group_members)
        self.assertNotIn(expired_member, group_members)


class UpdateSecurityGroupTestCase(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
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
            "Description was not updated"
        )

