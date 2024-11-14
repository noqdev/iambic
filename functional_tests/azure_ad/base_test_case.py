from __future__ import annotations

import asyncio
import random
from unittest import IsolatedAsyncioTestCase

from functional_tests.conftest import IAMBIC_TEST_DETAILS
from iambic.plugins.v0_1_0.azure_ad.group.models import GroupTemplateProperties
from iambic.plugins.v0_1_0.azure_ad.group.utils import list_groups
from iambic.plugins.v0_1_0.azure_ad.user.models import UserTemplateProperties
from iambic.plugins.v0_1_0.azure_ad.user.utils import list_users


class BaseMS365TestCase(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.ms_users: list[UserTemplateProperties] = asyncio.run(
            list_users(IAMBIC_TEST_DETAILS.config.azure_ad.organizations[0])
        )
        cls.ms_groups: list[GroupTemplateProperties] = asyncio.run(
            list_groups(IAMBIC_TEST_DETAILS.config.azure_ad.organizations[0])
        )

    def get_random_user(
        self, excluded_user_ids: list[str] = None
    ) -> UserTemplateProperties:
        while True:
            user = random.choice(self.ms_users)
            if not excluded_user_ids or user.user_id not in excluded_user_ids:
                return user

    def get_random_group(
        self, excluded_group_ids: list[str] = None, required_group_type="Security"
    ) -> GroupTemplateProperties:
        while True:
            group = random.choice(self.ms_groups)
            if not excluded_group_ids or group.group_id not in excluded_group_ids:
                if not required_group_type:
                    return group
                elif (
                    required_group_type == "Security"
                    and "Unified" not in group.group_types
                ):
                    return group
                elif required_group_type in group.group_types:
                    return group
