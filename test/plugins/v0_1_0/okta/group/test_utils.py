from __future__ import annotations

from test.plugins.v0_1_0.okta.test_utils import (  # noqa: F401 # intentional for mocks
    mock_okta_organization,
)

import pytest

from iambic.core.models import ProposedChangeType
from iambic.plugins.v0_1_0.okta.group.utils import (
    create_group,
    get_group,
    list_all_groups,
    list_all_users,
    list_group_users,
    maybe_delete_group,
    update_group_description,
    update_group_members,
    update_group_name,
)
from iambic.plugins.v0_1_0.okta.user.models import (
    OktaUserTemplate,
    OktaUserTemplateProperties,
)
from iambic.plugins.v0_1_0.okta.user.utils import create_user


@pytest.mark.asyncio
async def test_list_all_users_with_no_users(
    mock_okta_organization,  # noqa: F811 # intentional for mocks
):
    okta_users = await list_all_users(mock_okta_organization)
    assert okta_users == []


@pytest.mark.asyncio
async def test_list_all_users_with_users(
    mock_okta_organization,  # noqa: F811 # intentional for mocks
):
    # Have to create user before getting it
    username = "example_username"
    idp_name = "example.org"
    user_properties = OktaUserTemplateProperties(
        username=username, idp_name=idp_name, profile={"login": username}
    )
    template = OktaUserTemplate(file_path="example", properties=user_properties)
    okta_user = await create_user(template, mock_okta_organization)

    # verify users
    okta_users = await list_all_users(mock_okta_organization)
    assert len(okta_users) == 1
    okta_user_iambic_model = okta_users[0]
    assert okta_user_iambic_model.username == okta_user.username


@pytest.mark.asyncio
async def test_create_group(
    mock_okta_organization,  # noqa: F811 # intentional for mocks
):
    # Have to create user before getting it
    group_name = "example_groupname"
    idp_name = "example.org"
    description = "example description"
    okta_group = await create_group(
        group_name, idp_name, description, mock_okta_organization
    )

    # verify users
    assert okta_group.idp_name == idp_name
    assert okta_group.name == group_name
    assert okta_group.description == description
    assert (
        okta_group.group_id == "0"
    )  # it's zero because its the first group id in the memory implementation


@pytest.mark.asyncio
async def test_update_group_members(
    mock_okta_organization,  # noqa: F811 # intentional for mocks
):
    # Have to create group before getting it
    group_name = "example_groupname"
    idp_name = "example.org"
    description = "example description"
    okta_group = await create_group(
        group_name,
        idp_name,
        description,
        mock_okta_organization,
    )
    okta_group = await list_group_users(okta_group, mock_okta_organization)
    assert len(okta_group.members) == 0

    # Have to create user before getting it
    username = "example_username"
    idp_name = "example.org"
    user_properties = OktaUserTemplateProperties(
        username=username, idp_name=idp_name, profile={"login": username}
    )
    template = OktaUserTemplate(file_path="example", properties=user_properties)
    okta_user = await create_user(
        template,
        mock_okta_organization,
    )

    # test add users
    new_members = [okta_user]
    proposed_changes = await update_group_members(
        okta_group,
        new_members,
        mock_okta_organization,
        {},
    )
    assert proposed_changes[0].change_type == ProposedChangeType.ATTACH

    okta_group = await list_group_users(okta_group, mock_okta_organization)
    assert len(okta_group.members) == 1

    # test remove users
    new_members = []
    proposed_changes = await update_group_members(
        okta_group,
        new_members,
        mock_okta_organization,
        {},
    )
    assert proposed_changes[0].change_type == ProposedChangeType.DETACH

    okta_group = await list_group_users(okta_group, mock_okta_organization)
    assert len(okta_group.members) == 0


@pytest.mark.asyncio
async def test_get_group(mock_okta_organization):  # noqa: F811 # intentional for mocks
    # Have to create group before getting it
    group_name = "example_groupname"
    idp_name = "example.org"
    description = "example description"
    okta_group = await create_group(
        group_name,
        idp_name,
        description,
        mock_okta_organization,
    )
    okta_group = await list_group_users(okta_group, mock_okta_organization)
    assert len(okta_group.members) == 0

    retrieved_okta_group = await get_group(
        "not-existing-group-id", group_name, mock_okta_organization
    )
    assert retrieved_okta_group.name == group_name


@pytest.mark.asyncio
async def test_update_group_name(
    mock_okta_organization,  # noqa: F811 # intentional for mocks
):
    # Have to create group before getting it
    group_name = "example_groupname"
    idp_name = "example.org"
    description = "example description"
    okta_group = await create_group(
        group_name,
        idp_name,
        description,
        mock_okta_organization,
    )
    okta_group = await list_group_users(okta_group, mock_okta_organization)
    assert len(okta_group.members) == 0

    new_group_name = "new_group_name"
    proposed_changes = await update_group_name(
        okta_group,
        new_group_name,
        mock_okta_organization,
        {},
    )
    assert proposed_changes[0].change_type == ProposedChangeType.UPDATE

    retrieved_okta_group = await get_group(
        "not-existing-group-id", new_group_name, mock_okta_organization
    )
    assert retrieved_okta_group.name == new_group_name


@pytest.mark.asyncio
async def test_update_group_description(
    mock_okta_organization,  # noqa: F811 # intentional for mocks
):
    # Have to create group before getting it
    group_name = "example_groupname"
    idp_name = "example.org"
    description = "example description"
    okta_group = await create_group(
        group_name,
        idp_name,
        description,
        mock_okta_organization,
    )
    okta_group = await list_group_users(okta_group, mock_okta_organization)
    assert len(okta_group.members) == 0

    new_group_description = "new description"
    proposed_changes = await update_group_description(
        okta_group,
        new_group_description,
        mock_okta_organization,
        {},
    )
    assert proposed_changes[0].change_type == ProposedChangeType.UPDATE

    retrieved_okta_group = await get_group(
        okta_group.group_id, None, mock_okta_organization
    )
    assert retrieved_okta_group.description == new_group_description


@pytest.mark.asyncio
async def test_maybe_delete_group(
    mock_okta_organization,  # noqa: F811 # intentional for mocks
):
    # Have to create group before getting it
    group_name = "example_groupname"
    idp_name = "example.org"
    description = "example description"
    okta_group = await create_group(
        group_name,
        idp_name,
        description,
        mock_okta_organization,
    )
    okta_group = await list_group_users(okta_group, mock_okta_organization)
    assert len(okta_group.members) == 0

    proposed_changes = await maybe_delete_group(
        True,
        okta_group,
        mock_okta_organization,
        {},
    )
    assert proposed_changes[0].change_type == ProposedChangeType.DELETE

    retrieved_okta_group = await get_group(
        okta_group.group_id, group_name, mock_okta_organization
    )
    assert retrieved_okta_group is None


@pytest.mark.asyncio
async def test_list_all_group(
    mock_okta_organization,  # noqa: F811 # intentional for mocks
):
    # Have to create group before getting it
    group_name = "example_groupname"
    idp_name = "example.org"
    description = "example description"
    okta_group = await create_group(
        group_name,
        idp_name,
        description,
        mock_okta_organization,
    )
    okta_group = await list_group_users(okta_group, mock_okta_organization)
    assert len(okta_group.members) == 0

    okta_groups = await list_all_groups(mock_okta_organization)
    assert len(okta_groups) == 1
    assert okta_groups[0].name == group_name
