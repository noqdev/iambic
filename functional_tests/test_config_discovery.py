from __future__ import annotations

from unittest import IsolatedAsyncioTestCase

from functional_tests.conftest import IAMBIC_TEST_DETAILS
from iambic.config.models import Config
from iambic.config.utils import aws_account_update_and_discovery


class ConfigDiscoveryTestCase(IsolatedAsyncioTestCase):
    async def test_aws_account_name_updated(self):
        config = Config.load(IAMBIC_TEST_DETAILS.config_path)
        await config.setup_aws_accounts()

        original_name = config.aws.accounts[0].account_name
        new_name = "new_name"
        config.aws.accounts[0].account_name = new_name

        await aws_account_update_and_discovery(
            config, IAMBIC_TEST_DETAILS.template_dir_path
        )

        account_names = [account.account_name for account in config.aws.accounts]
        self.assertIn(original_name, account_names)
        self.assertNotIn(new_name, account_names)

    async def test_aws_account_discovered(self):
        config = Config.load(IAMBIC_TEST_DETAILS.config_path)
        await config.setup_aws_accounts()
        original_aws_count = len(config.aws.accounts)
        removed_account = config.aws.accounts[-1]
        config.aws.accounts.pop(-1)

        await aws_account_update_and_discovery(
            config, IAMBIC_TEST_DETAILS.template_dir_path
        )
        self.assertEqual(len(config.aws.accounts), original_aws_count)
        self.assertIn(
            removed_account.account_id,
            [account.account_id for account in config.aws.accounts],
        )
