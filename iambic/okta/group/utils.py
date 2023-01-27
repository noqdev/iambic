from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, List, Optional

import okta.models as models

from iambic.config.models import OktaOrganization
from iambic.core.context import ExecutionContext
from iambic.core.logger import log
from iambic.core.models import ProposedChange, ProposedChangeType
from iambic.okta.models import Group, User

if TYPE_CHECKING:
    from iambic.okta.group.models import UserSimple


async def list_all_users(okta_organization: OktaOrganization) -> List[User]:
    """
    List all users in Okta.

    Args:
    - okta_organization: An instance of the OktaOrganization class, which provides access to the Okta API.

    Returns:
    - A list of `User` instances, representing the users in Okta.
    """

    client = await okta_organization.get_okta_client()
    users, resp, err = await client.list_users()
    while resp.has_next():
        next_users, resp, err = await client.list_users()
        if err:
            log.error("Error encountered when listing users", error=str(err))
            return []
        users.append(next_users)

    users_to_return = []
    for user in users:
        users_to_return.append(
            User(
                idp_name=okta_organization.idp_name,
                username=user.profile.login,
                status=user.status.value.lower(),
                extra=dict(
                    okta_user_id=user.id,
                    created=user.created,
                ),
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
    users, resp, err = await client.list_group_users(group.extra["okta_group_id"])
    if err:
        raise Exception("Error listing users")

    while resp.has_next():
        next_users, resp, err = await client.list_group_users(
            group.extra["okta_group_id"]
        )
        if err:
            log.error("Error encountered when listing users in group", error=str(err))
            return group
        users.append(next_users)
    users_to_return = []
    for user in users:
        users_to_return.append(
            User(
                idp_name=okta_organization.idp_name,
                username=user.profile.login,
                status=user.status.value.lower(),
                attributes={},
                extra=dict(
                    okta_user_id=user.id,
                    created=user.created,
                ),
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
    groups, resp, err = await client.list_groups()
    while resp.has_next():
        next_groups, resp, err = await client.list_groups()
        if err:
            log.error("Error encountered when listing users", error=str(err))
            return []
        groups.append(next_groups)

    tasks = []
    groups_to_return = []
    for group_raw in groups:
        group = Group(
            idp_name=okta_organization.idp_name,
            name=group_raw.profile.name,
            description=group_raw.profile.description,
            group_id=group_raw.id,
            attributes=dict(),
            extra=dict(
                okta_group_id=group_raw.id,
                created=group_raw.created,
            ),
        )
        tasks.append(list_group_users(group, okta_organization))
    groups_to_return = await asyncio.gather(*tasks)
    return groups_to_return


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
        group, resp, err = await client.get_group(group_id)
    if not group:
        # Try to get group by name
        groups, resp, err = await client.list_groups(query_params={"q": group_name})
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
            okta_group_id=group.id,
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
    context: ExecutionContext,
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
    if context.execute:
        group, resp, err = await client.create_group(group_model)
        if err:
            raise Exception("Error creating group")
        group = Group(
            idp_name=idp_name,
            name=group_name,
            description=description,
            group_id=group.id,
            attributes=dict(),
            extra=dict(
                okta_group_id=group.id,
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
    context: ExecutionContext,
) -> List[ProposedChange]:
    """
    Update the name of a group in Okta.

    Args:
        group (Group): The group to update the name of.
        new_name (str): The new name for the group.
        okta_organization (OktaOrganization): The Okta organization to update the group in.
        log_params (dict): Logging parameters.
        context (ExecutionContext): The context object containing the execution flag.

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
    if context.execute:
        client = await okta_organization.get_okta_client()
        updated_group, resp, err = await client.update_group(
            group.extra["okta_group_id"], group_model
        )
        if err:
            raise Exception("Error updating group")
        Group(
            idp_name=okta_organization.idp_name,
            name=updated_group.profile.name,
            description=updated_group.profile.description,
            group_id=updated_group.id,
            attributes=dict(),
            extra=dict(
                okta_group_id=updated_group.id,
                created=updated_group.created,
            ),
        )
    return response


async def update_group_description(
    group: Group,
    new_description: str,
    okta_organization: OktaOrganization,
    log_params: dict[str, str],
    context: ExecutionContext,
) -> List[ProposedChange]:
    """
    Update the description of a group in Okta.

    Args:
        group (Group): The group to update the description of.
        new_description (str): The new description for the group.
        okta_organization (OktaOrganization): The Okta organization to update the group in.
        log_params (dict): Logging parameters.
        context (object): The context object containing the execution flag.

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
        )
    )
    if context.execute:
        new_group, resp, err = await client.update_group(
            group.extra["okta_group_id"], group_model
        )
        if err:
            raise Exception("Error updating group")
        Group(
            idp_name=okta_organization.idp_name,
            name=new_group.profile.name,
            description=new_group.profile.description,
            group_id=new_group.id,
            attributes=dict(),
            extra=dict(
                okta_group_id=new_group.id,
                created=new_group.created,
            ),
        )
    return response


async def update_group_members(
    group: Group,
    new_members: List[UserSimple],
    okta_organization: OktaOrganization,
    log_params: dict[str, str],
    context: ExecutionContext,
) -> List[ProposedChange]:
    """
    Update the members of a group in Okta.

    Args:
        group (Group): The group to update the members of.
        new_members (List[UserSimple]): The new members to add to the group.
        okta_organization (OktaOrganization): The Okta organization to update the group in.
        log_params (dict): Logging parameters.
        context (object): The context object containing the execution flag.

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
            )
        )

    if context.execute:
        for user in users_to_remove:
            user_okta, _, err = await client.get_user(user)
            if err:
                log.error("Error retrieving user", user=user, **log_params)
                continue
            _, err = await client.remove_user_from_group(
                group.extra["okta_group_id"], user_okta.id
            )
            if err:
                log.error(
                    "Error removing user to group",
                    user=user,
                    group=group.name,
                    **log_params,
                )
                continue

        for user in users_to_add:
            user_okta, _, err = await client.get_user(user)
            if err:
                log.error("Error retrieving user", user=user, **log_params)
                continue
            _, err = await client.add_user_to_group(
                group.extra["okta_group_id"], user_okta.id
            )
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
    context: ExecutionContext,
) -> List[ProposedChange]:
    """
    Delete a group in Okta.

    Args:
        group (Group): The group to delete.
        okta_organization (OktaOrganization): The Okta organization to delete the group from.
        log_params (dict): Logging parameters.
        context (object): The context object containing the execution flag.

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
        )
    )
    if context.execute:
        _, err = await client.delete_group(group.extra["okta_group_id"])
        if err:
            raise Exception("Error deleting group")
    return response
