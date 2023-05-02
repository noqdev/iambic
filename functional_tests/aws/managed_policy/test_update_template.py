from __future__ import annotations

import asyncio
from unittest import IsolatedAsyncioTestCase

from functional_tests.aws.managed_policy.utils import (
    generate_managed_policy_template_from_base,
)
from functional_tests.conftest import IAMBIC_TEST_DETAILS

from iambic.core import noq_json as json
from iambic.output.text import screen_render_resource_changes
from iambic.plugins.v0_1_0.aws.models import Tag


class ManagedPolicyUpdateTestCase(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = asyncio.run(
            generate_managed_policy_template_from_base(
                IAMBIC_TEST_DETAILS.template_dir_path
            )
        )
        cls.all_account_ids = [
            account.account_id for account in IAMBIC_TEST_DETAILS.config.aws.accounts
        ]
        # Only include the template in half the accounts
        # Make the accounts explicit so it's easier to validate account scoped tests
        cls.template.included_accounts = cls.all_account_ids[
            : len(cls.all_account_ids) // 2
        ]
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config.aws))

    @classmethod
    def tearDownClass(cls):
        cls.template.deleted = True
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config.aws))

    # tag None string value is not acceptable
    async def test_update_tag_with_bad_input(self):
        self.template.properties.tags = [Tag(key="*", value="")]  # bad input
        template_change_details = await self.template.apply(
            IAMBIC_TEST_DETAILS.config.aws,
        )
        screen_render_resource_changes([template_change_details])

        self.assertGreater(
            len(template_change_details.exceptions_seen),
            0,
            json.dumps(template_change_details.dict()),
        )
