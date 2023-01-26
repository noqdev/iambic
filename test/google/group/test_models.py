from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from iambic.core.models import merge_model
from iambic.google.group.models import GroupTemplateProperties, get_group_template

VALUE_UNDER_TEST = {
    "members": [
        {
            "kind": "admin#directory#member",
            "etag": '"FOO"',
            "id": "123",
            "email": "admin@example.com",
            "role": "OWNER",
            "type": "USER",
            "status": "ACTIVE",
        },
        {
            "kind": "admin#directory#member",
            "etag": '"BAR"',
            "id": "456",
            "email": "unverifable@external.com",
            "role": "MEMBER",
            "type": "USER",
        },
    ]
}

TEST_GOOGLE_GROUP = {
    "email": "example-google-group@example.com",
    "name": "Example Google Group",
    "description": "Google Group under test",
}


@pytest.fixture
def google_group_service():
    mock = MagicMock()
    mock.members = MagicMock()
    mock.members().list = MagicMock()
    mock.members().list().execute = MagicMock(return_value=VALUE_UNDER_TEST)
    return mock


@pytest.mark.asyncio
async def test_get_group_template(google_group_service):
    template = await get_group_template(
        google_group_service, TEST_GOOGLE_GROUP, "example-com"
    )
    assert len(template.properties.members) == len(VALUE_UNDER_TEST["members"])


def test_merge_list_group_members_expires_at():
    existing_members = [
        {
            "email": "user@example.com",
            "expires_at": "in 3 days",
        }
    ]
    existing_document = GroupTemplateProperties(
        name="bar",
        domain="foo",
        description="baz",
        email="bar@example.com",
        members=existing_members,
    )
    new_members = [
        {
            "email": "user@example.com",
        },
        {
            "email": "someone_else@example.com",
        },
    ]
    new_document = GroupTemplateProperties(
        name="bar",
        domain="foo",
        description="baz",
        email="bar@example.com",
        members=new_members,
    )
    merged_document: GroupTemplateProperties = merge_model(
        existing_document, new_document
    )
    assert existing_members != new_members
    assert merged_document.members[0].email == "user@example.com"
    assert (
        merged_document.members[0].expires_at == existing_document.members[0].expires_at
    )
