from __future__ import annotations

import uuid
from random import randint
from test.plugins.v0_1_0.azure_ad.test_utils import (  # noqa: F401 # intentional for mocks
    MockAzureADOrganization,
    azure_ad_organization,
)

import pytest
from aiohttp import ClientResponseError

from iambic.plugins.v0_1_0.azure_ad.group.models import Member, MemberDataType
from iambic.plugins.v0_1_0.azure_ad.group.utils import (
    create_group,
    delete_group,
    get_group,
    list_groups,
    update_group_attributes,
    update_group_members,
)
from iambic.plugins.v0_1_0.azure_ad.user.utils import create_user


@pytest.mark.asyncio
async def test_list_groups_success(
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
):
    # Test list_groups with successful response
    azure_ad_organization.request_data["groups"] = {
        "group_id_1": {
            "id": "group_id_1",
            "displayName": "Group 1 displayName",
            "mailEnabled": True,
            "mailNickname": "group1",
            "securityEnabled": True,
            "description": "Group 1 Description",
            "groupTypes": [],
        },
        "group_id_2": {
            "id": "group_id_2",
            "displayName": "Group 2 displayName",
            "mailEnabled": True,
            "mailNickname": "group2",
            "securityEnabled": True,
            "description": "Group 2 Description",
            "groupTypes": [],
        },
    }

    groups = await list_groups(azure_ad_organization)

    # Check if the returned list of groups has the correct length
    assert len(groups) == 2

    # Check if the returned groups have the correct properties
    assert groups[0].group_id == "group_id_1"
    assert groups[0].mail_nickname == "group1"
    assert groups[1].group_id == "group_id_2"
    assert groups[1].mail_nickname == "group2"


@pytest.mark.asyncio
async def test_list_groups_empty(
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
):
    # Test list_groups with empty response (no groups found)
    groups = await list_groups(azure_ad_organization)

    # Check if the returned list of groups is empty
    assert len(groups) == 0


@pytest.mark.asyncio
async def test_create_group_success(
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
):
    # Test create group with successful response

    group_suffix = randint(0, 100000)
    group_name = f"group{group_suffix}"
    group = await create_group(
        azure_ad_organization,
        group_name=group_name,
        description="Group Description",
        mail_nickname=group_name,
        mail_enabled=True,
        security_enabled=True,
        group_types=[],
    )

    group_data = azure_ad_organization.request_data["groups"].get(group.group_id)
    assert bool(group_data)
    assert group_data["displayName"] == group_name


@pytest.mark.asyncio
async def test_get_group_by_id_success(
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
):
    # Test get group by id with successful response

    group_suffix = randint(0, 100000)
    group_name = f"group{group_suffix}"
    group = await create_group(
        azure_ad_organization,
        group_name=group_name,
        description="Group Description",
        mail_nickname=group_name,
        mail_enabled=True,
        security_enabled=True,
        group_types=[],
    )

    response = await get_group(azure_ad_organization, group_id=group.group_id)
    assert response.name == group_name


@pytest.mark.asyncio
async def test_get_group_by_id_not_found(
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
):
    # Test get non-existent group by id with client error
    with pytest.raises(ClientResponseError):
        await get_group(azure_ad_organization, group_id=str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_get_group_by_name_success(
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
):
    # Test get group by name with successful response

    group_suffix = randint(0, 100000)
    group_name = f"group{group_suffix}"
    group = await create_group(
        azure_ad_organization,
        group_name=group_name,
        description="Group Description",
        mail_nickname=group_name,
        mail_enabled=True,
        security_enabled=True,
        group_types=[],
    )
    assert bool(azure_ad_organization.request_data["groups"].get(group.group_id))

    response = await get_group(azure_ad_organization, group_name=group_name)
    assert group.group_id == response.group_id


@pytest.mark.asyncio
async def test_get_group_by_name_not_found(
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
):
    # Test attempt get non-existent group by name
    with pytest.raises(Exception):
        await get_group(azure_ad_organization, group_name=str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_delete_group_success(
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
):
    # Test delete group

    group_suffix = randint(0, 100000)
    group_name = f"group{group_suffix}"
    group = await create_group(
        azure_ad_organization,
        group_name=group_name,
        description="Group Description",
        mail_nickname=group_name,
        mail_enabled=True,
        security_enabled=True,
        group_types=[],
    )
    assert bool(azure_ad_organization.request_data["groups"].get(group.group_id))

    await delete_group(azure_ad_organization, group, log_params={})

    assert not bool(azure_ad_organization.request_data["groups"].get(group.group_id))


@pytest.mark.asyncio
async def test_attempt_delete_nonexistent_group(
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
):
    # Test attempting to delete a non-existent group

    group_suffix = randint(0, 100000)
    group_name = f"group{group_suffix}"
    group = await create_group(
        azure_ad_organization,
        group_name=group_name,
        description="Group Description",
        mail_nickname=group_name,
        mail_enabled=True,
        security_enabled=True,
        group_types=[],
    )
    group.group_id = "nonexistent_group_id"
    response = await delete_group(azure_ad_organization, group=group, log_params={})
    assert len(response[0].exceptions_seen) > 0


@pytest.mark.asyncio
async def test_update_group(
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
):
    group_suffix = randint(0, 100000)
    group_name = f"group{group_suffix}"
    group = await create_group(
        azure_ad_organization,
        group_name=group_name,
        description="Group Description",
        mail_nickname=group_name,
        mail_enabled=True,
        security_enabled=True,
        group_types=[],
    )
    template_group = group.copy()
    template_group.description = "Updated Group Description"

    await update_group_attributes(
        azure_ad_organization, template_group, group, log_params={}
    )

    group_data = azure_ad_organization.request_data["groups"].get(group.group_id)
    assert group_data["description"] == template_group.description


@pytest.mark.asyncio
async def test_attempt_update_nonexistent_group(
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
):
    group_suffix = randint(0, 100000)
    group_name = f"group{group_suffix}"
    group = await create_group(
        azure_ad_organization,
        group_name=group_name,
        description="Group Description",
        mail_nickname=group_name,
        mail_enabled=True,
        security_enabled=True,
        group_types=[],
    )
    group.group_id = "nonexistent_group_id"
    template_group = group.copy()
    template_group.description = "Updated Group Description"

    response = await update_group_attributes(
        azure_ad_organization, template_group, group, log_params={}
    )
    assert len(response[0].exceptions_seen) > 0


@pytest.mark.asyncio
async def test_add_user_member_to_group(
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
):
    suffix = randint(0, 100000)
    username = f"user{suffix}@example.com"
    user = await create_user(
        azure_ad_organization,
        username=username,
        mail_nickname=f"user{suffix}",
        display_name=f"user{suffix}",
    )
    group_name = f"group{suffix}"
    group = await create_group(
        azure_ad_organization,
        group_name=group_name,
        description="Group Description",
        mail_nickname=group_name,
        mail_enabled=True,
        security_enabled=True,
        group_types=[],
    )

    await update_group_members(
        azure_ad_organization,
        group,
        [Member(id=user.user_id, name=user.username, data_type=MemberDataType.USER)],
        {},
    )

    group_data = azure_ad_organization.request_data["groups"].get(group.group_id)
    assert user.user_id in [member["id"] for member in group_data["members"]]


@pytest.mark.asyncio
async def test_add_and_retrieve_multi_member_to_group(
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
):
    suffix = randint(0, 100000)
    username = f"user{suffix}@example.com"
    user = await create_user(
        azure_ad_organization,
        username=username,
        mail_nickname=f"user{suffix}",
        display_name=f"user{suffix}",
    )
    group_name = f"group{suffix}"
    group = await create_group(
        azure_ad_organization,
        group_name=group_name,
        description="Group Description",
        mail_nickname=group_name,
        mail_enabled=True,
        security_enabled=True,
        group_types=[],
    )
    member_group_name = f"group{suffix}"
    member_group = await create_group(
        azure_ad_organization,
        group_name=member_group_name,
        description="Group Description",
        mail_nickname=member_group_name,
        mail_enabled=True,
        security_enabled=True,
        group_types=[],
    )

    await update_group_members(
        azure_ad_organization,
        group,
        [
            Member(id=user.user_id, name=user.username, data_type=MemberDataType.USER),
            Member(
                id=member_group.group_id,
                name=member_group_name,
                data_type=MemberDataType.GROUP,
            ),
        ],
        {},
    )

    group_resp = await get_group(azure_ad_organization, group.group_id)
    assert len(group_resp.members) == 2
    assert member_group.group_id in [member.id for member in group_resp.members]
    assert user.user_id in [member.id for member in group_resp.members]


@pytest.mark.asyncio
async def test_add_bad_user_member_to_group(
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
):
    suffix = randint(0, 100000)
    group_name = f"group{suffix}"
    group = await create_group(
        azure_ad_organization,
        group_name=group_name,
        description="Group Description",
        mail_nickname=group_name,
        mail_enabled=True,
        security_enabled=True,
        group_types=[],
    )
    response = await update_group_members(
        azure_ad_organization,
        group,
        [Member(id=str(uuid.uuid4()), name="Fake User", data_type=MemberDataType.USER)],
        {},
    )
    assert len(response[0].exceptions_seen) > 0


@pytest.mark.asyncio
async def test_remove_user_member_from_group(
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
):
    suffix = randint(0, 100000)
    username = f"user{suffix}@example.com"
    user = await create_user(
        azure_ad_organization,
        username=username,
        mail_nickname=f"user{suffix}",
        display_name=f"user{suffix}",
    )
    group_name = f"group{suffix}"
    group = await create_group(
        azure_ad_organization,
        group_name=group_name,
        description="Group Description",
        mail_nickname=group_name,
        mail_enabled=True,
        security_enabled=True,
        group_types=[],
    )

    await update_group_members(
        azure_ad_organization,
        group,
        [Member(id=user.user_id, name=user.username, data_type=MemberDataType.USER)],
        {},
    )

    group_data = azure_ad_organization.request_data["groups"].get(group.group_id)
    assert user.user_id in [member["id"] for member in group_data["members"]]

    group.members = [
        Member(id=user.user_id, name=user.username, data_type=MemberDataType.USER)
    ]
    await update_group_members(azure_ad_organization, group, [], {})

    group_data = azure_ad_organization.request_data["groups"].get(group.group_id)
    assert user.user_id not in [member["id"] for member in group_data["members"]]
