from __future__ import annotations

import pytest

from iambic.core.utils import sort_dict, sort_list_of_dicts_with_list_value


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


@pytest.mark.parametrize(
    "test_input,expected",
    [
        (
            [
                {
                    "included_accounts": ["b", "c"],
                    "users": ["bc@example.com"],
                },
                {
                    "users": ["ab@example.com"],
                    "included_accounts": ["b", "a"],
                },
            ],
            [
                {
                    "users": ["ab@example.com"],
                    "included_accounts": ["b", "a"],
                },
                {
                    "included_accounts": ["b", "c"],
                    "users": ["bc@example.com"],
                },
            ],
        )
    ],
)
def test_sort_list_of_dicts_with_list_value(test_input, expected):
    assert (
        sort_list_of_dicts_with_list_value(test_input, "included_accounts") == expected
    )
