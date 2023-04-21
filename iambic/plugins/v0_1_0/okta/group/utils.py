from __future__ import annotations

import asyncio
import functools
from typing import TYPE_CHECKING, List, Optional

import okta.models as models
from okta.models.user_status import UserStatus as OktaUserStatus

from iambic.core.context import ctx
from iambic.core.logger import log
from iambic.core.models import ProposedChange, ProposedChangeType
from iambic.core.utils import GlobalRetryController
from iambic.plugins.v0_1_0.okta.models import Group, User
from iambic.plugins.v0_1_0.okta.utils import generate_user_profile, handle_okta_fn

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.okta.group.models import UserSimple
    from iambic.plugins.v0_1_0.okta.iambic_plugin import OktaOrganization


async def list_all_users(okta_organization: OktaOrganization) -> List[User]:
    """
    List all users in Okta.

    Args:
    - okta_organization: An instance of the OktaOrganization class, which provides access to the Okta API.

    Returns:
    - A list of `User` instances, representing the users in Okta.
    """

    client = await okta_organization.get_okta_client()

    filter_operator = " OR ".join(
        [
            f'status eq "{status}"'
            for status in list(map(lambda s: s.name, list(OktaUserStatus)))
        ]
    )

    async with GlobalRetryController(
        fn_identifier="okta.list_users"
    ) as retry_controller:
        fn = functools.partial(
            client.list_users, query_params=dict(filter=filter_operator)
        )
        users, resp, err = await retry_controller(handle_okta_fn, fn)
        if err:
            log.error("Error encountered when listing users", error=str(err))
            raise Exception(f"Error listing users: {str(err)}")

    while resp.has_next():
        async with GlobalRetryController(
            fn_identifier="okta.list_users"
        ) as retry_controller:
            next_users, err = await retry_controller(handle_okta_fn, resp.next)
        if err:
            log.error("Error encountered when listing users", error=str(err))
            raise Exception(f"Error listing users: {str(err)}")
        users.append(next_users)

    if not users:
        return []

    users_to_return = []
    for user in users:
        users_to_return.append(
            User(
                user_id=user.id,
                idp_name=okta_organization.idp_name,
                username=user.profile.login,
                status=user.status.value.lower(),
                extra=dict(
                    created=user.created,
                ),
                profile=await generate_user_profile(user),
            )
        )
    return users_to_return


async def list_group_users(group: Group, okta_organization: OktaOrganization) -> Group:
    """
    List the members of a group in Okta.

    Args:
    - group: An instance of the `Group` class, representing the group whose members we want to list.
    - okta_organization: An instance of the OktaOrganization class, which provides access to the Okta API.

    Returns:
    - The same instance of the `Group` class, with the `members` attribute populated with a list of `User` instances,
    representing the members of the group.
    """

    client = await okta_organization.get_okta_client()
    async with GlobalRetryController(
        fn_identifier="okta.list_group_users"
    ) as retry_controller:
        fn = functools.partial(client.list_group_users, group.group_id)
        users, resp, err = await retry_controller(handle_okta_fn, fn)
        if err:
            log.error("Error encountered when listing users in group", error=str(err))
            raise Exception(f"Error listing users for group: {group.name}, {str(err)}")

    while resp.has_next():
        async with GlobalRetryController(
            fn_identifier="okta.list_group_users"
        ) as retry_controller:
            next_users, err = await retry_controller(handle_okta_fn, resp.next)
        if err:
            log.error("Error encountered when listing users in group", error=str(err))
            raise Exception(f"Error listing users for group: {group.name}, {str(err)}")
        users.append(next_users)

    if not users:
        # if there is really no users, we need to update our local knowledge of membership
        group.members = []
        return group

    users_to_return = []
    for user in users:
        users_to_return.append(
            User(
                user_id=user.id,
                idp_name=okta_organization.idp_name,
                username=user.profile.login,
                status=user.status.value.lower(),
                extra=dict(
                    created=user.created,
                ),
                profile=await generate_user_profile(user),
            )
        )
    group.members = users_to_return
    return group


async def list_all_groups(okta_organization: OktaOrganization) -> List[Group]:
    """
    List all groups in Okta.

    Args:
    - okta_organization: An instance of the OktaOrganization class, which provides access to the Okta API.

    Returns:
    - A list of `Group` instances, representing the groups in Okta.
    """

    client = await okta_organization.get_okta_client()
    async with GlobalRetryController(
        fn_identifier="okta.list_groups"
    ) as retry_controller:
        fn = functools.partial(client.list_groups)
        groups, resp, err = await retry_controller(handle_okta_fn, fn)
        if err:
            log.error("Error encountered when listing groups", error=str(err))
            raise Exception(f"Error listing groups: {str(err)}")

    while resp.has_next():
        async with GlobalRetryController(
            fn_identifier="okta.list_groups"
        ) as retry_controller:
            next_groups, err = await retry_controller(handle_okta_fn, resp.next)
        if err:
            log.error("Error encountered when listing groups", error=str(err))
            raise Exception(f"Error listing groups: {str(err)}")
        groups.append(next_groups)

    if not groups:
        log.info(
            "No groups found in Okta Organization",
            okta_organization=okta_organization.idp_name,
        )
        return []
    tasks = []
    for group_raw in groups:
        group = Group(
            idp_name=okta_organization.idp_name,
            name=group_raw.profile.name,
            description=group_raw.profile.description,
            group_id=group_raw.id,
            attributes=dict(),
            extra=dict(
                created=group_raw.created,
            ),
        )
        tasks.append(list_group_users(group, okta_organization))
    return list(await asyncio.gather(*tasks))


async def get_group(
    group_id: str, group_name: str, okta_organization: OktaOrganization
) -> Optional[Group]:
    """
    Get a group from Okta using the okta library.

    Args:
    - group_id: The ID of the group to get.
    - group_name: The name of the group to get.
    - okta_organization: An instance of the OktaOrganization class, which provides access to the Okta API.

    Returns:
    - An instance of the `Group` class, representing the retrieved group. If an error occurs, returns None.
    """
    # Get a group from Okta using the okta library
    client = await okta_organization.get_okta_client()
    group = None
    if group_id:
        async with GlobalRetryController(
            fn_identifier="okta.get_group"
        ) as retry_controller:
            fn = functools.partial(client.get_group, group_id)
            group, resp, err = await retry_controller(handle_okta_fn, fn)
    if not group:
        # Try to get group by name
        async with GlobalRetryController(
            fn_identifier="okta.list_groups"
        ) as retry_controller:
            fn = functools.partial(client.list_groups, query_params={"q": group_name})
            groups, resp, err = await retry_controller(handle_okta_fn, fn)
        if err:
            log.error(
                "Error encountered when getting group by name",
                group_id=group_id,
                group_name=group_name,
                error=str(err),
            )
            return None
        matching_group = None
        for matching_group in groups:
            if matching_group.profile.name == group_name:
                group = matching_group
                break

        if not group:
            return None
    if err:
        log.error(
            "Error encountered when getting group",
            group_id=group_id,
            group_name=group_name,
            error=str(err),
        )
        return None

    group = Group(
        idp_name=okta_organization.idp_name,
        name=group.profile.name,
        description=group.profile.description,
        group_id=group.id,
        attributes=dict(),
        extra=dict(
            created=group.created,
        ),
    )
    group = await list_group_users(group, okta_organization)
    return group


async def create_group(
    group_name: str,
    idp_name: str,
    description: str,
    okta_organization: OktaOrganization,
) -> Optional[Group]:
    """
    Create a new group in Okta.

    Args:
        group_name (str): The name of the group to create.
        idp_name (str): The IDP name for the group.
        description (str): The description for the group.
        okta_organization (OktaOrganization): The Okta organization to create the group in.

    Returns:
        Group: The created Group object.
    """

    # TODO: Need ProposedChanges, support context.execute = False
    client = await okta_organization.get_okta_client()

    group_profile = models.GroupProfile(
        {
            "name": group_name,
            "description": description,
        }
    )

    # Create the group
    group_model = models.Group({"profile": group_profile})
    if ctx.execute:
        async with GlobalRetryController(
            fn_identifier="okta.create_group"
        ) as retry_controller:
            fn = functools.partial(client.create_group, group_model)
            group, resp, err = await retry_controller(handle_okta_fn, fn)
        if err:
            raise Exception("Error creating group")
        group = Group(
            idp_name=idp_name,
            name=group_name,
            description=description,
            group_id=group.id,
            attributes=dict(),
            extra=dict(
                created=group.created,
            ),
        )
        return group
    return None


async def update_group_name(
    group: Group,
    new_name: str,
    okta_organization: OktaOrganization,
    log_params: dict[str, str],
) -> List[ProposedChange]:
    """
    Update the name of a group in Okta.

    Args:
        group (Group): The group to update the name of.
        new_name (str): The new name for the group.
        okta_organization (OktaOrganization): The Okta organization to update the group in.
        log_params (dict): Logging parameters.

    Returns:
        List[ProposedChange]: A list of proposed changes to be applied.
    """

    response: list[ProposedChange] = []
    if group.name == new_name:
        return response
    response.append(
        ProposedChange(
            change_type=ProposedChangeType.UPDATE,
            resource_id=group.group_id,
            resource_type=group.resource_type,
            attribute="group_name",
            current_value=group.name,
            new_value=new_name,
        )
    )
    group_model = models.Group(
        {
            "profile": models.GroupProfile(
                {
                    "name": new_name,
                    "description": group.description,
                }
            )
        }
    )
    if ctx.execute:
        client = await okta_organization.get_okta_client()
        async with GlobalRetryController(
            fn_identifier="okta.update_group"
        ) as retry_controller:
            fn = functools.partial(client.update_group, group.group_id, group_model)
            updated_group, resp, err = await retry_controller(handle_okta_fn, fn)
        if err:
            raise Exception("Error updating group")
        Group(
            idp_name=okta_organization.idp_name,
            name=updated_group.profile.name,
            description=updated_group.profile.description,
            group_id=updated_group.id,
            attributes=dict(),
            extra=dict(
                created=updated_group.created,
            ),
        )
    return response


async def update_group_description(
    group: Group,
    new_description: str,
    okta_organization: OktaOrganization,
    log_params: dict[str, str],
) -> List[ProposedChange]:
    """
    Update the description of a group in Okta.

    Args:
        group (Group): The group to update the description of.
        new_description (str): The new description for the group.
        okta_organization (OktaOrganization): The Okta organization to update the group in.
        log_params (dict): Logging parameters.

    Returns:
        List[ProposedChange]: A list of proposed changes to be applied.
    """
    response: list[ProposedChange] = []
    if group.description == new_description:
        return response
    client = await okta_organization.get_okta_client()
    group_model = models.Group(
        {
            "profile": models.GroupProfile(
                {
                    "name": group.name,
                    "description": new_description,
                }
            )
        }
    )
    response.append(
        ProposedChange(
            change_type=ProposedChangeType.UPDATE,
            resource_id=group.group_id,
            resource_type=group.resource_type,
            attribute="description",
            change_summary={
                "current_description": group.description,
                "proposed_description": new_description,
            },
            current_value=group.description,
            new_value=new_description,
        )
    )
    if ctx.execute:
        async with GlobalRetryController(
            fn_identifier="okta.update_group"
        ) as retry_controller:
            fn = functools.partial(client.update_group, group.group_id, group_model)
            new_group, resp, err = await retry_controller(handle_okta_fn, fn)
        if err:
            raise Exception("Error updating group")
        Group(
            idp_name=okta_organization.idp_name,
            name=new_group.profile.name,
            description=new_group.profile.description,
            group_id=new_group.id,
            attributes=dict(),
            extra=dict(
                created=new_group.created,
            ),
        )
    return response


async def update_group_members(
    group: Group,
    new_members: List[UserSimple],
    okta_organization: OktaOrganization,
    log_params: dict[str, str],
) -> List[ProposedChange]:
    """
    Update the members of a group in Okta.

    Args:
        group (Group): The group to update the members of.
        new_members (List[UserSimple]): The new members to add to the group.
        okta_organization (OktaOrganization): The Okta organization to update the group in.
        log_params (dict): Logging parameters.

    Returns:
        List[ProposedChange]: A list of proposed changes to be applied.
    """

    client = await okta_organization.get_okta_client()
    response = []
    current_user_usernames = [user.username for user in group.members]
    desired_user_usernames = [user.username for user in new_members]
    users_to_remove = [
        user for user in current_user_usernames if user not in desired_user_usernames
    ]

    users_to_add = [
        user for user in desired_user_usernames if user not in current_user_usernames
    ]

    if users_to_remove:
        response.append(
            ProposedChange(
                change_type=ProposedChangeType.DETACH,
                resource_id=group.group_id,
                resource_type=group.resource_type,
                attribute="users",
                change_summary={"UsersToRemove": list(users_to_remove)},
                current_value=current_user_usernames,
                new_value=users_to_remove,
            )
        )

    if users_to_add:
        response.append(
            ProposedChange(
                change_type=ProposedChangeType.ATTACH,
                resource_id=group.group_id,
                resource_type=group.resource_type,
                attribute="users",
                change_summary={"UsersToAdd": list(users_to_add)},
                current_value=current_user_usernames,
                new_value=users_to_add,
            )
        )

    if ctx.execute:
        for user in users_to_remove:
            async with GlobalRetryController(
                fn_identifier="okta.get_user"
            ) as retry_controller:
                fn = functools.partial(client.get_user, user)
                user_okta, _, err = await retry_controller(handle_okta_fn, fn)
            if err:
                log.error("Error retrieving user", user=user, **log_params)
                continue
            async with GlobalRetryController(
                fn_identifier="okta.remove_user_from_group"
            ) as retry_controller:
                fn = functools.partial(
                    client.remove_user_from_group,
                    group.group_id,
                    user_okta.id,
                )
                _, err = await retry_controller(handle_okta_fn, fn)
            if err:
                log.error(
                    "Error removing user from group",
                    user=user,
                    group=group.name,
                    **log_params,
                )
                continue

        for user in users_to_add:
            async with GlobalRetryController(
                fn_identifier="okta.get_user"
            ) as retry_controller:
                fn = functools.partial(client.get_user, user)
                user_okta, _, err = await retry_controller(handle_okta_fn, fn)
            if err:
                log.error("Error retrieving user", user=user, **log_params)
                continue
            async with GlobalRetryController(
                fn_identifier="okta.add_user_to_group"
            ) as retry_controller:
                fn = functools.partial(
                    client.add_user_to_group, group.group_id, user_okta.id
                )
                _, err = await retry_controller(handle_okta_fn, fn)
            if err:
                log.error(
                    "Error adding user to group",
                    user=user,
                    group=group.name,
                    **log_params,
                )
                continue
    return response


async def maybe_delete_group(
    delete: bool,
    group: Group,
    okta_organization: OktaOrganization,
    log_params: dict[str, str],
) -> List[ProposedChange]:
    """
    Delete a group in Okta.

    Args:
        group (Group): The group to delete.
        okta_organization (OktaOrganization): The Okta organization to delete the group from.
        log_params (dict): Logging parameters.

    Returns:
        List[ProposedChange]: A list of proposed changes to be applied.
    """
    response: list[ProposedChange] = []
    client = await okta_organization.get_okta_client()
    if not delete:
        return response
    response.append(
        ProposedChange(
            change_type=ProposedChangeType.DELETE,
            resource_id=group.group_id,
            resource_type=group.resource_type,
            attribute="group",
            change_summary={"group": group.name},
            current_value=group.name,
            new_value=None,
        )
    )
    if ctx.execute:
        async with GlobalRetryController(
            fn_identifier="okta.delete_group"
        ) as retry_controller:
            fn = functools.partial(client.delete_group, group.group_id)
            _, err = await retry_controller(handle_okta_fn, fn)
        if err:
            raise Exception("Error deleting group")
    return response
