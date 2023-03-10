from __future__ import annotations

from iambic.plugins.v0_1_0.okta.group.models import OktaGroupTemplateProperties


def test_members_sorting():

    members = [
        {"username": "user_1@example.org"},
        {"username": "user_2@example.org"},
    ]
    properties_1 = OktaGroupTemplateProperties(
        name="example_group",
        idp_name="example.org",
        group_id="example.org-example_group",
        members=members,
    )
    members_1 = properties_1.members
    members_2 = list(reversed(members_1))
    assert members_1 != members_2  # because we reverse the list
    properties_1.members = members_2
    assert (
        properties_1.members == members_2
    )  # double check the list is reversed because validation doesn't happen after creation
    properties_1.validate_model_afterward()
    assert properties_1.members == members_1
