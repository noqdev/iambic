from __future__ import annotations

import os
from unittest import IsolatedAsyncioTestCase

from functional_tests.aws.managed_policy.utils import (
    generate_managed_policy_template_from_base,
)
from functional_tests.conftest import IAMBIC_TEST_DETAILS
from iambic.core import noq_json as json
from iambic.output.text import screen_render_resource_changes
from iambic.plugins.v0_1_0.aws.models import Tag


class ManagedPolicyUpdateTestCase(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.template = await generate_managed_policy_template_from_base(
            IAMBIC_TEST_DETAILS.template_dir_path
        )
        self.all_account_ids = [
            account.account_id for account in IAMBIC_TEST_DETAILS.config.aws.accounts
        ]
        # only test the first two accounts for speed
        self.template.included_accounts = self.all_account_ids[0:2]

    async def asyncTearDown(self):
        if os.path.exists(self.template.file_path):
            self.template.deleted = True
            await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)

    # tag None string value is not acceptable
    async def test_update_tag_with_bad_input(self):
        self.template.properties.tags = [
            Tag(key="a", value=""),
            Tag(key="a", value=""),
        ]  # bad input because no repeating tag
        template_change_details = await self.template.apply(
            IAMBIC_TEST_DETAILS.config.aws,
        )
        screen_render_resource_changes([template_change_details])

        self.assertGreater(
            len(template_change_details.exceptions_seen),
            0,
            json.dumps(template_change_details.dict()),
        )
