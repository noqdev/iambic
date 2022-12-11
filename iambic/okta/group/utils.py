import asyncio
from typing import List

import okta.models as models

from iambic.config.models import OktaOrganization
from iambic.core.logger import log
from iambic.core.models import ProposedChange, ProposedChangeType
from iambic.okta.models import Group, User


async def list_all_users(okta_organization: OktaOrganization) -> List[User]:
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
    # Get a group from Okta using the okta library
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
            return [], str(err)
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


async def get_group(group_id, group_name, okta_organization: OktaOrganization):
    # Get a group from Okta using the okta library
    client = await okta_organization.get_okta_client()
    group, resp, err = await client.get_group(group_id)
    if err:
        log.error(
            "Error encountered when getting group",
            group_id=group_id,
            group_name=group_name,
            error=str(err),
        )
        return None

    if err:
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
):
    # TODO: Need ProposedChanges, support context.execute = False
    client = await okta_organization.get_okta_client()

    group_profile = models.GroupProfile(
        {
            "name": group_name,
        }
    )

    # Create the group
    group_model = models.Group({"profile": group_profile})
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


async def update_group_name(
    group: Group,
    new_name: str,
    okta_organization: OktaOrganization,
    log_params,
    context,
) -> List[ProposedChange]:
    response = []
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
    client = await okta_organization.get_okta_client()
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
        group, resp, err = await client.update_group(
            group.extra["okta_group_id"], group_model
        )
        if err:
            raise Exception("Error updating group")
        Group(
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
    return response


async def update_group_description(
    group: Group,
    new_description: str,
    okta_organization: OktaOrganization,
    log_params,
    context,
) -> List[ProposedChange]:
    response = []
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
    new_members: List[User],
    okta_organization: OktaOrganization,
    log_params,
    context,
) -> List[ProposedChange]:
    client = await okta_organization.get_okta_client()
    response = []
    users_to_remove = []
    users_to_add = []

    current_user_usernames = [user.username for user in group.members]
    desired_user_usernames = [user.username for user in new_members]
    for user in current_user_usernames:
        if user not in desired_user_usernames:
            users_to_remove.append(user)
    for user in desired_user_usernames:
        if user not in current_user_usernames:
            users_to_add.append(user)

    if users_to_remove:
        response.append(
            ProposedChange(
                change_type=ProposedChangeType.DETACH,
                resource_id=group.group_id,
                resource_type=group.resource_type,
                attribute="users",
                change_summary={"UsersToRemove": [user for user in users_to_remove]},
            )
        )
    if users_to_add:
        response.append(
            ProposedChange(
                change_type=ProposedChangeType.ATTACH,
                resource_id=group.group_id,
                resource_type=group.resource_type,
                attribute="users",
                change_summary={"UsersToAdd": [user for user in users_to_add]},
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
                    **log_params
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
                    **log_params
                )
                continue
    return response
