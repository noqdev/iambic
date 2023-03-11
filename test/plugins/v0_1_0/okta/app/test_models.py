from __future__ import annotations

from iambic.plugins.v0_1_0.okta.app.models import OktaAppTemplateProperties


def test_members_sorting():

    assignments = [
        {"user": "user_1@example.org"},
        {"group": "group@example.org"},
    ]
    properties_1 = OktaAppTemplateProperties(
        name="example_app",
        idp_name="example.org",
        id="example.org-example_app",
        assignments=assignments,
    )
    assignments_1 = properties_1.assignments
    assignments_2 = list(reversed(assignments_1))
    assert assignments_1 != assignments_2  # because we reverse the list
    properties_1.assignments = assignments_2
    assert (
        properties_1.assignments == assignments_2
    )  # double check the list is reversed because validation doesn't happen after creation
    properties_1.validate_model_afterward()
    assert properties_1.assignments == assignments_1
