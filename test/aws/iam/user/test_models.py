from __future__ import annotations

from iambic.core.template_generation import merge_model
from iambic.plugins.v0_1_0.aws.iam.user.models import Group, UserProperties


def test_merge_group(aws_accounts):

    existing_group = Group(
        group_name="foo",
        expires_at="tomorrow",
    )
    new_group = Group(group_name="foo")
    merged_group: Group = merge_model(new_group, existing_group, aws_accounts)
    assert existing_group.expires_at != new_group.expires_at
    assert merged_group.expires_at == existing_group.expires_at


def test_merge_user_properties(aws_accounts):

    existing_groups = [
        {
            "group_name": "bar",
            "expires_at": "tomorrow",
        }
    ]
    existing_properties = UserProperties(
        user_name="foo",
        groups=existing_groups,
    )
    new_groups = [
        {
            "group_name": "baz",
        },
        {
            "group_name": "bar",
        },
    ]
    new_properties = UserProperties(
        user_name="foo",
        groups=new_groups,
    )
    merged_properties: UserProperties = merge_model(
        new_properties, existing_properties, aws_accounts
    )
    assert merged_properties.groups[0].group_name == "bar"
    assert (
        merged_properties.groups[0].expires_at
        == existing_properties.groups[0].expires_at
    )
    assert merged_properties.groups[1].group_name == "baz"


def test_user_properties_sorting():
    groups = [
        {
            "group_name": "baz",
        },
        {
            "group_name": "bar",
        },
    ]
    properties = UserProperties(
        user_name="foo",
        groups=groups,
    )
    assert properties.groups[0].group_name == "bar"
    assert properties.groups[1].group_name == "baz"
