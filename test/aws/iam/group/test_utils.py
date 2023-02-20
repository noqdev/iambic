from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, call, patch

from iambic.core.models import ProposedChange, ProposedChangeType


class IamGroupUtilsTestCase(unittest.TestCase):
    @patch("iambic.aws.iam.group.utils.paginated_search")
    def test_get_group_inline_policy_names(self, paginated_search_mock):
        from iambic.aws.iam.group.utils import group_inline_policy_names

        iam_client_mock = MagicMock()
        paginated_search_mock.return_value = ["policy1", "policy2"]

        result = asyncio.run(
            get_group_inline_policy_names("group_name", iam_client_mock)
        )

        self.assertEqual(result, ["policy1", "policy2"])
        paginated_search_mock.assert_called_with(
            iam_client_mock.list_group_policies, "PolicyNames", GroupName="group_name"
        )

    @patch("iambic.aws.iam.group.utils.paginated_search")
    def test_list_groups(self, paginated_search_mock):
        from iambic.aws.iam.group.utils import list_groups

        iam_client_mock = MagicMock()
        paginated_search_mock.return_value = [
            {"group_name": "group1"},
            {"group_name": "group2"},
        ]

        result = asyncio.run(list_groups(iam_client_mock))

        self.assertEqual(result, [{"group_name": "group1"}, {"group_name": "group2"}])
        paginated_search_mock.assert_called_with(iam_client_mock.list_groups, "Groups")

    @patch("iambic.aws.iam.group.utils.paginated_search")
    def test_list_users_in_group(self, paginated_search_mock):
        from iambic.aws.iam.group.utils import list_users_in_group

        iam_client_mock = MagicMock()
        paginated_search_mock.return_value = [
            {"user_name": "user1"},
            {"user_name": "user2"},
        ]

        result = asyncio.run(list_users_in_group("group_name", iam_client_mock))

        self.assertEqual(result, [{"user_name": "user1"}, {"user_name": "user2"}])
        paginated_search_mock.assert_called_with(
            iam_client_mock.get_group, "Users", GroupName="group_name"
        )

    @patch("iambic.aws.iam.group.utils.boto_crud_call")
    def test_get_group_policy(self, boto_crud_call_mock):
        from iambic.aws.iam.group.utils import get_group_policy

        iam_client_mock = MagicMock()
        boto_crud_call_mock.return_value = {
            "PolicyName": "policy_name",
            "PolicyDocument": {"Statement": [{"Action": "iam:*", "Effect": "Allow"}]},
        }

        result = asyncio.run(
            get_group_policy("group_name", "policy_name", iam_client_mock)
        )

        self.assertEqual(
            result,
            {
                "PolicyName": "policy_name",
                "PolicyDocument": {
                    "Statement": [{"Action": "iam:*", "Effect": "Allow"}]
                },
            },
        )
        boto_crud_call_mock.assert_called_with(
            iam_client_mock.get_group_policy,
            GroupName="group_name",
            PolicyName="policy_name",
        )

    @patch("iambic.aws.iam.group.utils.get_group_policy")
    @patch("iambic.aws.iam.group.utils.get_group_inline_policy_names")
    def test_get_group_inline_policies(
        self, get_group_inline_policy_names_mock, get_group_policy_mock
    ):
        from iambic.aws.iam.group.utils import get_group_inline_policies

        iam_client_mock = MagicMock()
        get_group_inline_policy_names_mock.return_value = ["policy1", "policy2"]
        get_group_policy_mock.side_effect = [
            {
                "PolicyName": "policy1",
                "PolicyDocument": {
                    "Statement": [{"Action": "iam:*", "Effect": "Allow"}]
                },
            },
            {
                "PolicyName": "policy2",
                "PolicyDocument": {
                    "Statement": [{"Action": "iam:*", "Effect": "Deny"}]
                },
            },
        ]

        result = asyncio.run(get_group_inline_policies("group_name", iam_client_mock))

        self.assertEqual(
            result,
            {
                "policy1": {"Statement": [{"Action": "iam:*", "Effect": "Allow"}]},
                "policy2": {"Statement": [{"Action": "iam:*", "Effect": "Deny"}]},
            },
        )
        get_group_inline_policy_names_mock.assert_called_with(
            "group_name", iam_client_mock
        )
        get_group_policy_mock.assert_has_calls(
            [
                call("group_name", "policy1", iam_client_mock),
                call("group_name", "policy2", iam_client_mock),
            ]
        )

    @patch("iambic.aws.iam.group.utils.boto_crud_call")
    def test_get_group_managed_policies(self, boto_crud_call_mock):
        from iambic.aws.iam.group.utils import get_group_managed_policies

        iam_client_mock = MagicMock()
        boto_crud_call_mock.side_effect = [
            {
                "AttachedPolicies": [
                    {
                        "PolicyName": "policy1",
                        "PolicyArn": "arn:aws:iam::aws:policy/AdministratorAccess",
                    },
                    {
                        "PolicyName": "policy2",
                        "PolicyArn": "arn:aws:iam::aws:policy/ReadOnlyAccess",
                    },
                ],
                "IsTruncated": True,
                "Marker": "marker",
            },
            {
                "AttachedPolicies": [
                    {
                        "PolicyName": "policy3",
                        "PolicyArn": "arn:aws:iam::aws:policy/PowerUserAccess",
                    },
                ],
                "IsTruncated": False,
            },
        ]

        result = asyncio.run(get_group_managed_policies("group_name", iam_client_mock))

        self.assertEqual(
            result,
            [
                {
                    "PolicyName": "policy1",
                    "PolicyArn": "arn:aws:iam::aws:policy/AdministratorAccess",
                },
                {
                    "PolicyName": "policy2",
                    "PolicyArn": "arn:aws:iam::aws:policy/ReadOnlyAccess",
                },
                {
                    "PolicyName": "policy3",
                    "PolicyArn": "arn:aws:iam::aws:policy/PowerUserAccess",
                },
            ],
        )
        boto_crud_call_mock.assert_has_calls(
            [
                call(
                    iam_client_mock.list_attached_group_policies,
                    GroupName="group_name",
                ),
                call(
                    iam_client_mock.list_attached_group_policies,
                    GroupName="group_name",
                    Marker="marker",
                ),
            ]
        )

    @patch("iambic.aws.iam.group.utils.get_group_managed_policies")
    @patch("iambic.aws.iam.group.utils.boto_crud_call")
    def test_get_group(self, boto_crud_call_mock, get_group_managed_policies_mock):
        from iambic.aws.iam.group.utils import get_group

        iam_client_mock = MagicMock()
        boto_crud_call_mock.return_value = {
            "Group": {
                "GroupName": "group_name",
                "CreateDate": "create_date",
                "Path": "path",
                "Arn": "arn",
            }
        }
        get_group_managed_policies_mock.return_value = [
            {
                "PolicyName": "policy1",
                "PolicyArn": "arn:aws:iam::aws:policy/AdministratorAccess",
            },
            {
                "PolicyName": "policy2",
                "PolicyArn": "arn:aws:iam::aws:policy/ReadOnlyAccess",
            },
        ]

        result = asyncio.run(get_group("group_name", iam_client_mock))

        self.assertEqual(
            result,
            {
                "GroupName": "group_name",
                "CreateDate": "create_date",
                "Path": "path",
                "Arn": "arn",
                "ManagedPolicies": [
                    {
                        "PolicyName": "policy1",
                        "PolicyArn": "arn:aws:iam::aws:policy/AdministratorAccess",
                    },
                    {
                        "PolicyName": "policy2",
                        "PolicyArn": "arn:aws:iam::aws:policy/ReadOnlyAccess",
                    },
                ],
            },
        )
        boto_crud_call_mock.assert_called_with(
            iam_client_mock.get_group, GroupName="group_name"
        )
        get_group_managed_policies_mock.assert_called_with(
            "group_name", iam_client_mock
        )

    @patch("iambic.aws.iam.group.utils.get_group")
    def test_get_group_across_accounts(self, get_group_mock):
        from iambic.aws.iam.group.utils import get_group_across_accounts

        aws_accounts = [AsyncMock(), AsyncMock()]
        get_group_mock.side_effect = [
            {
                "GroupName": "group_name",
                "CreateDate": "create_date",
                "Path": "path",
                "Arn": "arn1",
            },
            {
                "GroupName": "group_name",
                "CreateDate": "create_date",
                "Path": "path",
                "Arn": "arn2",
            },
        ]

        result = asyncio.run(get_group_across_accounts(aws_accounts, "group_name"))

        self.assertEqual(
            result,
            {
                aws_accounts[0].account_id: {
                    "GroupName": "group_name",
                    "CreateDate": "create_date",
                    "Path": "path",
                    "Arn": "arn1",
                },
                aws_accounts[1].account_id: {
                    "GroupName": "group_name",
                    "CreateDate": "create_date",
                    "Path": "path",
                    "Arn": "arn2",
                },
            },
        )

    @patch("iambic.aws.iam.group.utils.boto_crud_call")
    @patch("iambic.aws.iam.group.utils.log")
    def test_apply_group_managed_policies(self, log_mock, boto_crud_call_mock):
        from iambic.aws.iam.group.utils import apply_group_managed_policies

        iam_client_mock = MagicMock()
        context_mock = MagicMock()
        context_mock.execute = True
        log_params = {"group_name": "group_name"}

        result = asyncio.run(
            apply_group_managed_policies(
                "group_name",
                iam_client_mock,
                [
                    {"PolicyName": "policy1", "PolicyArn": "arn1"},
                    {"PolicyName": "policy2", "PolicyArn": "arn2"},
                ],
                [
                    {"PolicyName": "policy1", "PolicyArn": "arn1"},
                    {"PolicyName": "policy3", "PolicyArn": "arn3"},
                ],
                log_params,
                context_mock,
            )
        )

        self.assertEqual(
            result,
            [
                ProposedChange(
                    change_type=ProposedChangeType.DETACH,
                    resource_id="arn3",
                    attribute="managed_policies",
                ),
                ProposedChange(
                    change_type=ProposedChangeType.ATTACH,
                    resource_id="arn2",
                    attribute="managed_policies",
                ),
            ],
        )
        boto_crud_call_mock.assert_any_call(
            iam_client_mock.detach_group_policy,
            GroupName="group_name",
            PolicyArn="arn3",
        )
        boto_crud_call_mock.assert_any_call(
            iam_client_mock.attach_group_policy,
            GroupName="group_name",
            PolicyArn="arn2",
        )
        log_mock.info.assert_any_call(
            "Stale managed policies discovered. Detachingmanaged policies...",
            managed_policies=["arn3"],
            **log_params,
        )
        log_mock.info.assert_any_call(
            "New managed policies discovered. Attaching managed policies...",
            managed_policies=["arn2"],
            **log_params,
        )


if __name__ == "__main__":
    unittest.main()
