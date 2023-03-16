from __future__ import annotations

from iambic.core.template_generation import merge_access_model_list
from iambic.plugins.v0_1_0.aws.iam.policy.models import AssumeRolePolicyDocument
from iambic.plugins.v0_1_0.aws.iam.role.models import RoleProperties, RoleTemplate
from iambic.plugins.v0_1_0.aws.iam.role.template_generation import (
    calculate_import_preference,
)


def test_calculate_import_preference():
    template = RoleTemplate(
        file_path="foo", identifier="foo", properties=RoleProperties(role_name="foo")
    )
    templatized_preferrence = calculate_import_preference(template)
    assert templatized_preferrence is False  # because we are not using variables

    template = RoleTemplate(
        file_path="foo",
        identifier="{{account_name}} admin",
        properties=RoleProperties(role_name="{{account_name}} admin"),
    )
    templatized_preferrence = calculate_import_preference(template)
    assert templatized_preferrence is True  # because we are using variables

    template = RoleTemplate(
        file_path="foo",
        identifier="{{account_name}} admin",
        properties=RoleProperties(role_name="{{account_name}} admin"),
    )
    # break template
    template.properties.description = lambda x: x  # lambda is not json-able
    templatized_preferrence = calculate_import_preference(template)
    assert templatized_preferrence is False  # because template preference crashed.


def test_merge_access_model_list_for_assume_role_policy_document(aws_accounts: list):

    existing_assume_role_policy = AssumeRolePolicyDocument()
    existing_assume_role_policy.included_accounts = [
        account.account_name for account in [aws_accounts[0], aws_accounts[1]]
    ]
    existing_list = [existing_assume_role_policy]
    for policy in existing_list:
        # the testing condition only matters if resourced_id is not unique
        assert policy.resource_id == ""

    new_assume_role_policy = AssumeRolePolicyDocument()
    new_assume_role_policy_include_accounts = [
        account.account_name for account in [aws_accounts[2]]
    ]
    new_assume_role_policy.included_accounts = new_assume_role_policy_include_accounts
    incoming_list = [
        new_assume_role_policy,
        existing_assume_role_policy.copy(deep=True),
    ]
    for policy in incoming_list:
        # the testing condition only matters if resourced_id is not unique
        assert policy.resource_id == ""

    assert (
        incoming_list[0] != existing_list[0]
    )  # this is to ensure we trigger the condition
    # in which incoming order has been mixed when we cannot relay on resource id

    considered_accounts = aws_accounts[0:3]
    merged_list = merge_access_model_list(
        incoming_list, existing_list, considered_accounts
    )
    incoming_assume_role_document: AssumeRolePolicyDocument = merged_list[0]
    assert (
        incoming_assume_role_document.included_accounts
        == new_assume_role_policy_include_accounts
    )
    existing_assume_role_document: AssumeRolePolicyDocument = merged_list[1]
    assert (
        existing_assume_role_document.included_accounts
        == existing_assume_role_policy.included_accounts
    )
