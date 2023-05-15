from __future__ import annotations

import uuid
from random import randint
from test.plugins.v0_1_0.azure_ad.test_utils import (  # noqa: F401 # intentional for mocks
    MockAzureADOrganization,
    azure_ad_organization,
)

import pytest
from aiohttp import ClientResponseError

from iambic.plugins.v0_1_0.azure_ad.user.utils import (
    create_user,
    delete_user,
    get_user,
    list_users,
    update_user_attributes,
)


@pytest.mark.asyncio
async def test_list_users_success(
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
):
    # Test list_users with successful response
    azure_ad_organization.request_data["users"] = {
        "user_id_1": {
            "id": "user_id_1",
            "userPrincipalName": "user1@example.com",
            "displayName": "User 1",
            "mailNickname": "user1",
        },
        "user_id_2": {
            "id": "user_id_2",
            "userPrincipalName": "user2@example.com",
            "mailNickname": "user2",
            "displayName": "User 2",
        },
    }

    users = await list_users(azure_ad_organization)

    # Check if the returned list of users has the correct length
    assert len(users) == 2

    # Check if the returned users have the correct properties
    assert users[0].user_id == "user_id_1"
    assert users[0].username == "user1@example.com"
    assert users[1].user_id == "user_id_2"
    assert users[1].username == "user2@example.com"


@pytest.mark.asyncio
async def test_list_users_empty(
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
):
    # Test list_users with empty response (no users found)
    users = await list_users(azure_ad_organization)

    # Check if the returned list of users is empty
    assert len(users) == 0


@pytest.mark.asyncio
async def test_create_user_success(
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
):
    # Test create user with successful response

    user_suffix = randint(0, 100000)
    username = f"user{user_suffix}@example.com"
    user = await create_user(
        azure_ad_organization,
        username=username,
        mail_nickname=f"user{user_suffix}",
        display_name=f"user{user_suffix}",
    )

    user_data = azure_ad_organization.request_data["users"].get(user.user_id)
    assert bool(user_data)
    assert user_data["userPrincipalName"] == username


@pytest.mark.asyncio
async def test_get_user_by_id_success(
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
):
    # Test get user by id with successful response

    user_suffix = randint(0, 100000)
    username = f"user{user_suffix}@example.com"
    user = await create_user(
        azure_ad_organization,
        username=username,
        mail_nickname=f"user{user_suffix}",
        display_name=f"user{user_suffix}",
    )

    response = await get_user(azure_ad_organization, user_id=user.user_id)
    assert user.username == response.username


@pytest.mark.asyncio
async def test_get_user_by_id_not_found(
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
):
    # Test get non-existent user by id with client error
    with pytest.raises(ClientResponseError):
        await get_user(azure_ad_organization, user_id=str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_get_user_by_username_success(
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
):
    # Test get user by username with successful response

    user_suffix = randint(0, 100000)
    username = f"user{user_suffix}@example.com"
    user = await create_user(
        azure_ad_organization,
        username=username,
        mail_nickname=f"user{user_suffix}",
        display_name=f"user{user_suffix}",
    )
    assert bool(azure_ad_organization.request_data["users"].get(user.user_id))

    response = await get_user(azure_ad_organization, username=user.username)
    assert user.user_id == response.user_id


@pytest.mark.asyncio
async def test_get_user_by_username_not_found(
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
):
    # Test attempt get non-existent user by username
    with pytest.raises(Exception):
        await get_user(azure_ad_organization, username=str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_delete_user_success(
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
):
    # Test delete user

    user_suffix = randint(0, 100000)
    username = f"user{user_suffix}@example.com"
    user = await create_user(
        azure_ad_organization,
        username=username,
        mail_nickname=f"user{user_suffix}",
        display_name=f"user{user_suffix}",
    )
    assert bool(azure_ad_organization.request_data["users"].get(user.user_id))

    await delete_user(azure_ad_organization, user=user, log_params={})

    assert not bool(azure_ad_organization.request_data["users"].get(user.user_id))


@pytest.mark.asyncio
async def test_attempt_delete_nonexistent_user(
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
):
    # Test attempting to delete a non-existent user
    user_suffix = randint(0, 100000)
    username = f"user{user_suffix}@example.com"
    user = await create_user(
        azure_ad_organization,
        username=username,
        mail_nickname=f"user{user_suffix}",
        display_name=f"user{user_suffix}",
    )
    user.user_id = "nonexistent_user_id"
    response = await delete_user(azure_ad_organization, user=user, log_params={})
    assert len(response[0].exceptions_seen) > 0


@pytest.mark.asyncio
async def test_update_user(
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
):
    user_suffix = randint(0, 100000)
    username = f"user{user_suffix}@example.com"
    user = await create_user(
        azure_ad_organization,
        username=username,
        mail_nickname=f"user{user_suffix}",
        display_name=f"user{user_suffix}",
    )
    template_user = user.copy()
    template_user.display_name = "new_display_name"

    await update_user_attributes(
        azure_ad_organization, template_user, user, log_params={}
    )

    user_data = azure_ad_organization.request_data["users"].get(user.user_id)
    assert user_data["displayName"] == template_user.display_name


@pytest.mark.asyncio
async def test_attempt_update_nonexistent_user(
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
):
    user_suffix = randint(0, 100000)
    username = f"user{user_suffix}@example.com"
    user = await create_user(
        azure_ad_organization,
        username=username,
        mail_nickname=f"user{user_suffix}",
        display_name=f"user{user_suffix}",
    )
    user.user_id = "nonexistent_user_id"
    template_user = user.copy()
    template_user.display_name = "new_display_name"

    response = await update_user_attributes(
        azure_ad_organization, template_user, user, log_params={}
    )
    assert len(response[0].exceptions_seen) > 0
