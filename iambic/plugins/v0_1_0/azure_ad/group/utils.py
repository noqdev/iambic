from __future__ import annotations

import asyncio
import functools
from typing import TYPE_CHECKING, List, Optional

from iambic.core.context import ctx
from iambic.core.models import ProposedChange, ProposedChangeType
from iambic.core.utils import GlobalRetryController
from iambic.plugins.v0_1_0.azure_ad.user.models import User, UserSimple

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.azure_ad.group.models import (
        Group,
        GroupTemplateProperties,
    )
    from iambic.plugins.v0_1_0.azure_ad.models import AzureADOrganization


async def list_group_users(
    azure_ad_organization: AzureADOrganization, group: Group
) -> Group:
    """
    List the members of a group in Azure AD.

    Args:
    - azure_ad_organization: An instance of the AzureADOrganization class, which provides access to the Microsoft Graph API.
    - group: An instance of the `Group` class, representing the group whose members we want to list.

    Returns:
    - The same instance of the `Group` class, with the `members` attribute populated with a list of `User` instances,
    representing the members of the group.
    """
    async with GlobalRetryController(
        fn_identifier="azure_ad.list_group_users"
    ) as retry_controller:
        fn = functools.partial(
            azure_ad_organization.list, f"groups/{group.group_id}/members"
        )
        members = await retry_controller(fn)

    users_to_return = []
    for member in members:
        user = await azure_ad_organization.get(f"users/{member.get('id')}")
        users_to_return.append(
            User.from_azure_response(azure_ad_organization.idp_name, user)
        )
    group.members = users_to_return
    return group


async def list_all_groups(
    azure_ad_organization: AzureADOrganization, include_members: bool = True
) -> List[Group]:
    from iambic.plugins.v0_1_0.azure_ad.group.models import Group

    async with GlobalRetryController(
        fn_identifier="azure_ad.list_groups"
    ) as retry_controller:
        fn = functools.partial(azure_ad_organization.list, "groups")
        groups = await retry_controller(fn)
        groups = [Group.from_azure_response(g) for g in groups]

    if not include_members:
        return groups

    tasks = []
    for group in groups:
        tasks.append(list_group_users(azure_ad_organization, group))
    return list(await asyncio.gather(*tasks))


async def get_group(
    azure_ad_organization: AzureADOrganization, group_id: str, group_name: str
) -> Optional[Group]:
    """
    Get a group from Azure AD using the Microsoft Graph API.

    Args:
    - azure_ad_organization: An instance of the AzureADOrganization class, which provides access to the Microsoft Graph API.
    - group_id: The ID of the group to get.
    - group_name: The name of the group to get.

    Returns:
    - An instance of the `Group` class, representing the retrieved group. If an error occurs, returns None.
    """
    group = None
    if group_id:
        async with GlobalRetryController(
            fn_identifier="azure_ad.get_group"
        ) as retry_controller:
            fn = functools.partial(
                azure_ad_organization.get, f"groups/{group.group_id}"
            )
            group = await retry_controller(fn)
            group = Group.from_azure_response(group)
    if not group:
        # Try to get group by name
        groups = await list_all_groups(azure_ad_organization, False)
        for g in groups:
            if g.display_name == group_name:
                group = g
                break
        if not group:
            return None
    return await list_group_users(azure_ad_organization, group)


async def create_group(
    azure_ad_organization: AzureADOrganization,
    group_name: str,
    idp_name: str,
    description: str,
) -> Optional[Group]:
    """
    Create a new group in Azure AD.
    Args:
    - azure_ad_organization (AzureADOrganization): The Azure AD organization to update the group in.
    - group_name: The name of the group to create.
    - idp_name: The IDP name for the group.
    - description: The description for the group.

    Returns:
    - An instance of the `Group` class, representing the created group. If an error occurs, returns None.
    """

    # TODO: Need ProposedChanges
    if ctx.execute:
        group = await azure_ad_organization.post(
            f"https://graph.windows.net/{idp_name}/groups",
            json={
                "displayName": group_name,
                "mailEnabled": False,
                "mailNickname": group_name,
                "securityEnabled": True,
                "description": description,
            },
        )
        return Group.from_azure_response(group)


async def update_group_attributes(
    azure_ad_organization: AzureADOrganization,
    template_group: GroupTemplateProperties,
    cloud_group: Group,
    log_params: dict[str, str],
) -> List[ProposedChange]:
    """
    Update the name of a group in Azure AD.
        Args:
        azure_ad_organization (AzureADOrganization): The Azure AD organization to update the group in.
        template_group (Group): The group to update the name of.
        new_name (str): The new name for the group.
        log_params (dict): Logging parameters.

    Returns:
        List[ProposedChange]: A list of proposed changes to be applied.
    """
    exclude_keys = {"group_id", "tenant_id", "members"}
    response: list[ProposedChange] = []
    patch_request = {}

    for attr, value in cloud_group.dict().items():
        if attr in exclude_keys:
            continue

        if (template_value := getattr(template_group, attr)) != value:
            patch_request[attr] = template_value
            response.append(
                ProposedChange(
                    change_type=ProposedChangeType.UPDATE,
                    resource_id=template_group.group_id,
                    resource_type=template_group.resource_type,
                    attribute=attr,
                    current_value=value,
                    new_value=template_value,
                )
            )
    if ctx.execute and patch_request:
        await azure_ad_organization.patch(
            f"groups/{template_group.group_id}",
            json=patch_request,
        )

    return response


async def update_group_members(
    azure_ad_organization: AzureADOrganization,
    group: Group,
    new_members: List[UserSimple],
    log_params: dict[str, str],
) -> List[ProposedChange]:
    """
    Update the members of a group in Azure AD.

    Args:
        azure_ad_organization (AzureADOrganization): The Azure AD organization to update the group in.
        group (Group): The group to update the members of.
        new_members (List[UserSimple]): The new members to add to the group.
        log_params (dict): Logging parameters.

    Returns:
        List[ProposedChange]: A list of proposed changes to be applied.
    """
    response = []
    current_member_ids = [member.id for member in group.members]
    desired_member_ids = [member.id for member in new_members]

    members_to_remove = [
        member for member in current_member_ids if member not in desired_member_ids
    ]
    members_to_add = [
        member for member in desired_member_ids if member not in current_member_ids
    ]

    if members_to_remove:
        response.append(
            ProposedChange(
                change_type=ProposedChangeType.DETACH,
                resource_id=group.group_id,
                resource_type=group.resource_type,
                attribute="members",
                change_summary={"MembersToRemove": list(members_to_remove)},
            )
        )
    if members_to_add:
        response.append(
            ProposedChange(
                change_type=ProposedChangeType.ATTACH,
                resource_id=group.group_id,
                resource_type=group.resource_type,
                attribute="members",
                change_summary={"MembersToAdd": list(members_to_add)},
            )
        )

    if ctx.execute:
        tasks = []

        for member_id in members_to_remove:
            tasks.append(
                azure_ad_organization.delete(
                    f"groups/{group.group_id}/members/{member_id}/$ref"
                )
            )

        for member_id in members_to_add:
            tasks.append(
                azure_ad_organization.post(
                    f"groups/{group.group_id}/members/$ref",
                    json={
                        "@odata.id": f"https://graph.windows.net/v1.0/directoryObjects/{member_id}"
                    },
                )
            )

        await asyncio.gather(*tasks)

    return response


async def delete_group(
    azure_ad_organization: AzureADOrganization,
    group: Group,
    log_params: dict[str, str],
) -> List[ProposedChange]:
    """
    Delete a group in Azure AD.
    Args:
        azure_ad_organization (AzureADOrganization): The Azure AD organization to delete the group from.
        group (Group): The group to delete.
        log_params (dict): Logging parameters.

    Returns:
        List[ProposedChange]: A list of proposed changes to be applied.
    """
    response: list[ProposedChange] = [
        ProposedChange(
            change_type=ProposedChangeType.DELETE,
            resource_id=group.group_id,
            resource_type=group.resource_type,
            attribute="group",
            change_summary={"group": group.name},
        )
    ]

    if ctx.execute:
        await azure_ad_organization.delete(f"groups/{group.group_id}")

    return response
