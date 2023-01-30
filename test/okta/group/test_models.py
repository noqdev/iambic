from __future__ import annotations

from iambic.core.models import merge_model
from iambic.okta.group.models import OktaGroupTemplateProperties


def test_merge_template_access_rules():
    existing_members = [{"username": "user@example.com", "expires_at": "tomorrow"}]
    existing_document = OktaGroupTemplateProperties(
        identifier="bar",
        file_path="foo",
        name="engineering",
        idp_name="3ks9",
        members=existing_members,
    )
    new_members = [
        {
            "username": "user@example.com",
        }
    ]
    new_document = OktaGroupTemplateProperties(
        identifier="bar",
        file_path="foo",
        name="engineering",
        idp_name="3ks9",
        members=new_members,
    )
    merged_document: OktaGroupTemplateProperties = merge_model(
        existing_document, new_document
    )
    assert existing_members != new_members
    assert merged_document.members[0].username == "user@example.com"
    assert (
        merged_document.members[0].expires_at == existing_document.members[0].expires_at
    )
