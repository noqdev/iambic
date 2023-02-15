from __future__ import annotations

import pytest

from iambic.plugins.aws.identity_center.permission_set.template_generation import (
    _sorted_and_clean_access_rules,
)


@pytest.mark.parametrize(
    "input,expected",
    [
        (
            [
                {
                    "included_accounts": ["space in account name"],
                    "included_orgs": ["xyz"],
                    "users": ["bob@example.com"],
                    "account_rule_key": "space in account name",
                },
                {
                    "included_accounts": ["global_account_name"],
                    "included_orgs": ["xyz"],
                    "users": ["alice@example.com"],
                    "account_rule_key": "global_account_name",
                },
            ],
            [
                {
                    "included_accounts": ["global_account_name"],
                    "included_orgs": ["xyz"],
                    "users": ["alice@example.com"],
                },
                {
                    "included_accounts": ["space in account name"],
                    "included_orgs": ["xyz"],
                    "users": ["bob@example.com"],
                },
            ],
        )
    ],
)
def test_sorted_and_clean_access_rules(input, expected):
    assert _sorted_and_clean_access_rules(input) == expected
