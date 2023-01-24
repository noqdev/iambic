from __future__ import annotations

import pytest

from iambic.core.utils import sort_dict


@pytest.mark.parametrize(
    "test_input,expected",
    [
        (
            {
                "access_rules": [
                    {
                        "users": ["bob@example.com"],
                        "included_accounts": [{"space in account name"}],
                        "included_orgs": ["xyz"],
                    },
                    {
                        "included_accounts": [{"global_account_name"}],
                        "included_orgs": ["xyz"],
                        "users": ["alice@example.com"],
                    },
                ]
            },
            {
                "access_rules": [
                    {
                        "included_accounts": [{"space in account name"}],
                        "included_orgs": ["xyz"],
                        "users": ["bob@example.com"],
                    },
                    {
                        "included_accounts": [{"global_account_name"}],
                        "included_orgs": ["xyz"],
                        "users": ["alice@example.com"],
                    },
                ]
            },
        )
    ],
)
def test_sort_dict_stability(test_input, expected):
    assert sort_dict(test_input) == expected
