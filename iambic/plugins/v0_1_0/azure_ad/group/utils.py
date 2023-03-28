from __future__ import annotations

import asyncio
import functools
from typing import TYPE_CHECKING, List, Optional

from aiohttp import ClientResponseError

from iambic.core.context import ctx
from iambic.core.logger import log
from iambic.core.models import ProposedChange, ProposedChangeType
from iambic.core.utils import GlobalRetryController, snake_to_camelback
from iambic.plugins.v0_1_0.azure_ad.group.models import (
    GroupTemplateProperties,
    Member,
    MemberDataType,
)
from iambic.plugins.v0_1_0.azure_ad.models import AzureADOrganization
from iambic.plugins.v0_1_0.azure_ad.user.utils import get_user

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.azure_ad.user.models import UserTemplateProperties


async def list_group_members(
    azure_ad_organization: AzureADOrganization,
    group: GroupTemplateProperties,
) -> GroupTemplateProperties:
    """
    List the members of a group in Azure AD.

    Args:
    - azure_ad_organization: An instance of the AzureADOrganization class, which provides access to the Microsoft Graph API.
    - group: An instance of the `GroupTemplateProperties` class, representing the group whose members we want to list.

    Returns:
    - The same instance of the `GroupTemplateProperties` class, with the `members` attribute populated with a list of `User` instances,
    representing the members of the group.
    """
    async with GlobalRetryController(
        fn_identifier="azure_ad.list_group_members"
    ) as retry_controller:
        fn = functools.partial(
            azure_ad_organization.list, f"groups/{group.group_id}/members"
        )
        members = await retry_controller(fn)

    if not members:
        return group

    user_members = list(
        await asyncio.gather(
            *[
                get_user(
                    azure_ad_organization,
                    user_id=member.get("id"),
                    allow_template_ref=True,
                )
                for member in members
                if member.get("@odata.type").endswith("user")
            ],
            return_exceptions=True,
        )
    )
    group.members = [
        Member(id=member.user_id, name=member.username, data_type=MemberDataType.USER)
        for member in user_members
    ]

    if len(user_members) != len(members):
        for member in members:
            if not member.get("@odata.type").endswith("group"):
                continue

            if (mail := member.get("mail")) and "@" in mail:
                name = mail
            else:
                name = member.get("displayName")

            group.members.append(
                Member(id=member["id"], name=name, data_type=MemberDataType.GROUP)
            )

    return group


async def list_groups(
    azure_ad_organization: AzureADOrganization, include_members: bool = True, **kwargs
) -> List[GroupTemplateProperties]:
    from iambic.plugins.v0_1_0.azure_ad.group.models import GroupTemplateProperties

    async with GlobalRetryController(
        fn_identifier="azure_ad.list_groups"
    ) as retry_controller:
        fn = functools.partial(azure_ad_organization.list, "groups", **kwargs)
        groups = await retry_controller(fn)
        groups = [GroupTemplateProperties.from_azure_response(g) for g in groups]

    if not include_members:
        return groups

    tasks = []
    for group in groups:
        tasks.append(list_group_members(azure_ad_organization, group))
    return list(await asyncio.gather(*tasks))


async def get_group(
    azure_ad_organization: AzureADOrganization,
    group_id: Optional[str] = None,
    group_name: Optional[str] = None,
) -> Optional[GroupTemplateProperties]:
    """
    Get a group from Azure AD using the Microsoft Graph API.

    Args:
    - azure_ad_organization: An instance of the AzureADOrganization class, which provides access to the Microsoft Graph API.
    - group_id: The ID of the group to get.
    - group_name: The name of the group to get.

    Returns:
    - An instance of the `GroupTemplateProperties` class, representing the retrieved group. If an error occurs, returns None.
    """
    assert group_id or group_name, "Must provide either group_id or group_name"

    if group_id:
        async with GlobalRetryController(
            fn_identifier="azure_ad.get_group"
        ) as retry_controller:
            fn = functools.partial(azure_ad_organization.get, f"groups/{group_id}")
            if group := await retry_controller(fn):
                group = GroupTemplateProperties.from_azure_response(group)
                return await list_group_members(azure_ad_organization, group)
            elif not group_name:
                raise Exception(f"Group not found with id {group_id}")

    # Try to get group by name
    groups = await list_groups(
        azure_ad_organization,
        include_members=True,
        params={"$filter": f"displayName eq '{group_name}'"},
    )
    if groups:
        return groups[0]

    raise Exception(f"Group not found with displayName {group_name}")


async def create_group(
    azure_ad_organization: AzureADOrganization,
    group_name: str,
    description: str,
    mail_enabled: bool,
    mail_nickname: Optional[str],
    security_enabled: bool,
    group_types: list[str],
) -> Optional[GroupTemplateProperties]:
    """
    Create a new group in Azure AD.
    Args:
    - azure_ad_organization (AzureADOrganization): The Azure AD organization to update the group in.
    - group_name: The name of the group to create.
    - idp_name: The IDP name for the group.
    - description: The description for the group.

    Returns:
    - An instance of the `GroupTemplateProperties` class, representing the created group. If an error occurs, returns None.
    """

    group = await azure_ad_organization.post(
        "groups",
        json={
            "displayName": group_name,
            "mailEnabled": mail_enabled,
            "mailNickname": mail_nickname,
            "securityEnabled": security_enabled,
            "description": description,
            "groupTypes": group_types,
        },
    )
    return GroupTemplateProperties.from_azure_response(group)


async def update_group_attributes(
    azure_ad_organization: AzureADOrganization,
    template_group: GroupTemplateProperties,
    cloud_group: GroupTemplateProperties,
    log_params: dict[str, str],
) -> List[ProposedChange]:
    """
    Update the name of a group in Azure AD.
        Args:
        azure_ad_organization (AzureADOrganization): The Azure AD organization to update the group in.
        template_user (GroupTemplateProperties): The template representation of the group.
        cloud_user (GroupTemplateProperties): The current representation of the group in the cloud.
        log_params (dict): Logging parameters.

    Returns:
        List[ProposedChange]: A list of proposed changes to be applied.
    """
    response: list[ProposedChange] = []
    patch_request = {}

    for attr, value in cloud_group.dict(
        exclude_none=False, exclude={"group_id", "members", "mail"}
    ).items():
        if (template_value := getattr(template_group, attr)) != value:
            response.append(
                ProposedChange(
                    change_type=ProposedChangeType.UPDATE,
                    resource_id=template_group.resource_id,
                    resource_type=template_group.resource_type,
                    attribute=attr,
                    current_value=value,
                    new_value=template_value,
                )
            )

            attr = "name" if attr == "display_name" else snake_to_camelback(attr)
            patch_request[attr] = template_value

    if ctx.execute and patch_request:
        try:
            await azure_ad_organization.patch(
                f"groups/{template_group.group_id}",
                json=patch_request,
            )
        except ClientResponseError as err:
            log.exception(
                "Failed to update group in Azure AD",
                **log_params,
            )
            response[0].exceptions_seen = [str(err)]

    return response


def parse_group_member_response(
    members: list[Member],
    proposed_change: ProposedChange,
    responses: list,
    log_params: dict,
) -> ProposedChange:
    for i, response in enumerate(responses):
        if isinstance(response, ClientResponseError):
            member = members[i]
            log.exception(
                "Failed to update group members in Azure AD",
                err=str(response),
                member=member.dict(),
                **log_params,
            )
            proposed_change.exceptions_seen.append(
                f"Failed to add or remove member. "
                f"Member: {member.name} ({member.data_type}). "
                f"Response: {response.status} - {response.message}."
            )
    return proposed_change


async def update_group_members(
    azure_ad_organization: AzureADOrganization,
    cloud_group: GroupTemplateProperties,
    template_members: List[Member],
    log_params: dict[str, str],
) -> List[ProposedChange]:
    """
    Update the members of a group in Azure AD.

    Args:
        azure_ad_organization (AzureADOrganization): The Azure AD organization to update the group in.
        cloud_group (GroupTemplateProperties): The group to update the members of.
        template_members (List[Member]): The new members to add to the group.
        log_params (dict): Logging parameters.

    Returns:
        List[ProposedChange]: A list of proposed changes to be applied.
    """
    response = []

    current_member_ids = [member.id for member in cloud_group.members]
    desired_member_ids = [member.id for member in template_members]

    members_to_remove = [
        member for member in cloud_group.members if member.id not in desired_member_ids
    ]
    members_to_add = [
        member for member in template_members if member.id not in current_member_ids
    ]

    if members_to_remove:
        response.append(
            ProposedChange(
                change_type=ProposedChangeType.DETACH,
                resource_id=cloud_group.resource_id,
                resource_type=cloud_group.resource_type,
                attribute="members",
                change_summary={
                    "MembersToRemove": [member.dict() for member in members_to_remove]
                },
                current_value=[member.name for member in cloud_group.members],
                new_value=[member.name for member in members_to_remove],
            )
        )

    if members_to_add:
        response.append(
            ProposedChange(
                change_type=ProposedChangeType.ATTACH,
                resource_id=cloud_group.resource_id,
                resource_type=cloud_group.resource_type,
                attribute="members",
                change_summary={
                    "MembersToAdd": [member.dict() for member in members_to_add]
                },
                current_value=[member.name for member in cloud_group.members],
                new_value=[member.name for member in members_to_add],
            )
        )

    if ctx.execute:
        tasks = []
        if members_to_remove:
            for member in members_to_remove:
                tasks.append(
                    azure_ad_organization.delete(
                        f"groups/{cloud_group.group_id}/members/{member.id}/$ref"
                    )
                )
        if members_to_add:
            for member in members_to_add:
                tasks.append(
                    azure_ad_organization.post(
                        f"groups/{cloud_group.group_id}/members/$ref",
                        json={
                            "@odata.id": f"https://graph.windows.net/v1.0/directoryObjects/{member.id}"
                        },
                    )
                )
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        if members_to_remove:
            response[0] = parse_group_member_response(
                members=members_to_remove,
                proposed_change=response[0],
                responses=list(responses[: len(members_to_remove)]),
                log_params=log_params,
            )

        if members_to_add:
            response_elem = 0 if not members_to_remove else 1
            response[response_elem] = parse_group_member_response(
                members=members_to_add,
                proposed_change=response[response_elem],
                responses=list(responses[len(members_to_remove) :]),
                log_params=log_params,
            )

    return response


async def delete_group(
    azure_ad_organization: AzureADOrganization,
    group: GroupTemplateProperties,
    log_params: dict[str, str],
) -> List[ProposedChange]:
    """
    Delete a group in Azure AD.
    Args:
        azure_ad_organization (AzureADOrganization): The Azure AD organization to delete the group from.
        group (GroupTemplateProperties): The group to delete.
        log_params (dict): Logging parameters.

    Returns:
        List[ProposedChange]: A list of proposed changes to be applied.
    """
    response: list[ProposedChange] = [
        ProposedChange(
            change_type=ProposedChangeType.DELETE,
            resource_id=group.resource_id,
            resource_type=group.resource_type,
            attribute="group",
            change_summary={"group": group.name},
            current_value=group.name,
            new_value=None,
        )
    ]

    if ctx.execute:
        try:
            await azure_ad_organization.delete(f"groups/{group.group_id}")
        except ClientResponseError as err:
            log.exception(
                "Failed to delete group in Azure AD",
                **log_params,
            )
            response[0].exceptions_seen = [str(err)]

    return response


async def resolve_member_ids(
    azure_ad_organization: AzureADOrganization, members: List[Member]
) -> List[Member]:
    from iambic.plugins.v0_1_0.azure_ad.group.utils import get_group
    from iambic.plugins.v0_1_0.azure_ad.user.utils import get_user

    for member in members:
        if member.id:
            continue
        if member.data_type == MemberDataType.USER:
            user_details: Optional[UserTemplateProperties] = await get_user(
                azure_ad_organization, username=member.name
            )
            if not user_details:
                continue
            member.id = user_details.user_id
        elif member.data_type == MemberDataType.GROUP:
            group_details: Optional[GroupTemplateProperties] = await get_group(
                azure_ad_organization, group_name=member.name
            )
            if not group_details:
                continue
            member.id = group_details.group_id
    return members
