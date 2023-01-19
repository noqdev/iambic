from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from iambic.core.template_generation import group_dict_attribute


@pytest.fixture
def mock_set_included_accounts_for_grouped_attribute():
    async_mock = AsyncMock()
    with patch(
        "iambic.core.template_generation.set_included_accounts_for_grouped_attribute",
        autospec=True,
        side_effect=async_mock,
    ):
        yield async_mock


@pytest.mark.asyncio
async def test_group_dict_attribute_for_sort_stability(
    mock_set_included_accounts_for_grouped_attribute,
):

    unsorted_grouped_attributes_a = [
        {
            "resource_val": {"policy_arn": "example-arn"},
            "included_accounts": ["*"],
        },
        {"resource_val": {"aws-partition": "example-arn"}, "included_accounts": ["*"]},
    ]

    mock_set_included_accounts_for_grouped_attribute.return_value = (
        unsorted_grouped_attributes_a
    )

    attributes = await group_dict_attribute({}, 2, [], is_dict_attr=True)

    assert attributes == [
        {"aws-partition": "example-arn"},
        {"policy_arn": "example-arn"},
    ]
