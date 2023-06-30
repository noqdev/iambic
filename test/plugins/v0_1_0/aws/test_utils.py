from __future__ import annotations

from unittest.mock import Mock

import pytest


@pytest.mark.parametrize(
    "caller_identity, expected_arn",
    [
        (
            {
                # simple user credentials
                "UserId": "AIDASAMPLEUSERID",
                "Account": "123456789012",
                "Arn": "arn:aws:iam::123456789012:user/DevAdmin",
            },
            "arn:aws:iam::123456789012:user/DevAdmin",
        ),
        (
            {
                # non-aws identity center role temp credentials
                "Account": "123456789012",
                "Arn": "arn:aws:sts::123456789012:assumed-role/my-role-name/my-role-session-name",
                "UserId": "AKIAI44QH8DHBEXAMPLE:my-role-session-name",
            },
            "arn:aws:iam::123456789012:role/my-role-name",
        ),
        (
            {
                # aws identity center role temp credentials
                "UserId": "fake-user-id:eample_user_1@example.com",
                "Account": "123456789012",
                "Arn": "arn:aws:sts::123456789012:assumed-role/AWSReservedSSO_AdministratorAccess_random_id/example_user_1@example.com",
            },
            "arn:aws:sts::123456789012:assumed-role/AWSReservedSSO_AdministratorAccess_random_id/example_user_1@example.com",
        ),
    ],
)
def test_get_identity_arn(caller_identity, expected_arn):
    from iambic.plugins.v0_1_0.aws.utils import get_identity_arn

    arn = get_identity_arn(caller_identity)
    assert arn == expected_arn


@pytest.mark.asyncio
async def test_process_import_rules():
    from iambic.plugins.v0_1_0.aws.iambic_plugin import (
        ImportAction,
        ImportRule,
        ImportRuleTag,
    )
    from iambic.plugins.v0_1_0.aws.utils import process_import_rules

    # Setup
    template_type = "NOQ::AWS::IAM::Role"
    identifier = "AWSServiceRoleForCloudFormationStackSetsOrgMember"
    tags = [{"key": "tagkey", "value": "tagvalue"}]
    resource_dict = {
        "path": "/aws-service-role/member.org.stacksets.cloudformation.amazonaws.com/",
        "role_name": "AWSServiceRoleForCloudFormationStackSetsOrgMember",
    }

    test_rules = [
        {
            "rules": [
                ImportRule(
                    match_tags=[ImportRuleTag(key="terraform")],
                    action=ImportAction.set_import_only,
                ),
            ],
            "result": [],
        },
        {
            "rules": [
                ImportRule(
                    match_tags=[ImportRuleTag(key="tagkey", value="tagvalue")],
                    action=ImportAction.set_import_only,
                )
            ],
            "result": [ImportAction.set_import_only],
        },
        {
            "rules": [
                ImportRule(match_names=["AWSReservedSSO*"], action=ImportAction.ignore)
            ],
            "result": [],
        },
        {
            "rules": [
                ImportRule(match_names=["AWSServiceRole*"], action=ImportAction.ignore)
            ],
            "result": [ImportAction.ignore],
        },
        {
            "rules": [
                ImportRule(
                    match_paths=["/service-role/*", "/aws-service-role/*"],
                    action=ImportAction.ignore,
                )
            ],
            "result": [ImportAction.ignore],
        },
        {
            "rules": [
                ImportRule(
                    match_tags=[{"key": "ManagedBy", "value": "CDK"}],
                    action=ImportAction.ignore,
                )
            ],
            "result": [],
        },
        {
            "rules": [
                ImportRule(
                    match_template_types=["NOQ::AWS::IAM::Role"],
                    match_tags=[ImportRuleTag(key="tagkey", value="tagvalue")],
                    action=ImportAction.set_import_only,
                )
            ],
            "result": [ImportAction.set_import_only],
        },
    ]
    for test_rule in test_rules:
        config_mock = Mock()
        config_mock.import_rules = test_rule["rules"]

        # Call function
        result = await process_import_rules(
            config_mock, template_type, identifier, tags, resource_dict
        )

        # Verify result
        assert result == test_rule["result"]
