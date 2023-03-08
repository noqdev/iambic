from __future__ import annotations

import asyncio
import functools
from typing import TYPE_CHECKING, List, Optional

import aiohttp
from msal.application import PublicClientApplication

# from msgraph.generated.groups.item.messages.messages_request_builder import MessagesRequestBuilder as GroupMessagesRequestBuilder
from msgraph.generated.connections.item.groups.groups_request_builder import (
    GroupsRequestBuilder,
)
from msgraph.generated.users.item.messages.messages_request_builder import (
    MessagesRequestBuilder as UserMessagesRequestBuilder,
)

from iambic.core.context import ExecutionContext
from iambic.core.logger import log
from iambic.core.models import ProposedChange, ProposedChangeType
from iambic.core.utils import GlobalRetryController
from iambic.plugins.v0_1_0.azure_ad.models import Group, User
from iambic.plugins.v0_1_0.azure_ad.utils import handle_azure_ad_fn

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.azure_ad.group.models import UserSimple
    from iambic.plugins.v0_1_0.azure_ad.iambic_plugin import AzureADOrganization


async def list_all_users(azure_ad_organization: AzureADOrganization) -> List[User]:
    """
    List all users in Azure AD.

    Args:
    - azure_ad_organization: An instance of the AzureADOrganization class, which provides access to the Azure AD API.

    Returns:
    - A list of `User` instances, representing the users in Azure AD.
    """

    client = await azure_ad_organization.get_azure_ad_client()
    async with GlobalRetryController(
        fn_identifier="azure_ad.list_users"
    ) as retry_controller:
        fn = functools.partial(client.users.list)
        users, err = await retry_controller(handle_azure_ad_fn, fn)
    if err:
        log.error("Error encountered when listing users", error=str(err))
        return []

    users_to_return = []
    for user in users:
        users_to_return.append(
            User(
                user_id=user.object_id,
                idp_name=azure_ad_organization.idp_name,
                username=user.user_principal_name,
                status=user.account_enabled,
                extra=dict(),
                profile=dict(
                    display_name=user.display_name,
                    mail=user.mail,
                    mail_nickname=user.mail_nickname,
                ),
            )
        )
    return users_to_return


async def list_group_users(group: Group, client: PublicClientApplication) -> Group:
    """
    List the members of a group in Azure AD.

    Args:
    - group: An instance of the `Group` class, representing the group whose members we want to list.
    - client: An instance of the `PublicClientApplication` class, which provides access to the Azure AD API.

    Returns:
    - The same instance of the `Group` class, with the `members` attribute populated with a list of `User` instances,
    representing the members of the group.
    """
    try:
        result = await client.get("/groups/{}/members".format(group.group_id))
    except Exception as error:
        log.error(f"Error listing users in group: {error}")
        return group

    members = result.get("value")
    users_to_return = []
    for member in members:
        user = await client.get("/users/{}".format(member.get("id")))
        users_to_return.append(
            User(
                user_id=user.get("id"),
                idp_name=group.idp_name,
                username=user.get("userPrincipalName"),
                status=user.get("accountEnabled"),
                extra=dict(
                    created=user.get("createdDateTime"),
                ),
                profile={
                    "display_name": user.get("displayName"),
                    "given_name": user.get("givenName"),
                    "surname": user.get("surname"),
                    "mail": user.get("mail"),
                },
            )
        )
    group.members = users_to_return
    return group


async def list_all_groups(azure_ad_organization: AzureADOrganization) -> List[Group]:
    client = await azure_ad_organization.get_azure_ad_client()
    request_config = GroupsRequestBuilder.GroupsRequestBuilderGetQueryParameters()
    try:
        groups = await client.groups.get(request_configuration=request_config)
    except Exception as e:
        print(e)

    # TODO: https://github.com/microsoftgraph/msgraph-sdk-python/blob/main/docs/samples.md
    query_params = MessagesRequestBuilder.MessagesRequestBuilderGetQueryParameters(
        select=[
            "subject",
        ],
        skip=1,
        top=5,
    )
    groups = await client.groups()
    tasks = []
    for group in groups:
        tasks.append(list_group_users(group, azure_ad_organization))
    return list(await asyncio.gather(*tasks))


async def get_group(
    group_id: str, group_name: str, azure_ad_organization: AzureADOrganization
) -> Optional[Group]:
    """
    Get a group from Azure AD using the Microsoft Graph API.

    Args:
    - group_id: The ID of the group to get.
    - group_name: The name of the group to get.
    - azure_ad_organization: An instance of the AzureADOrganization class, which provides access to the Microsoft Graph API.

    Returns:
    - An instance of the `Group` class, representing the retrieved group. If an error occurs, returns None.
    """
    client = await azure_ad_organization.get_client()
    group = None
    if group_id:
        async with GlobalRetryController(
            fn_identifier="azure_ad.get_group"
        ) as retry_controller:
            fn = functools.partial(client.groups.get, group_id)
            group, err = await retry_controller(fn)
    if not group:
        # Try to get group by name
        async with GlobalRetryController(
            fn_identifier="azure_ad.list_groups"
        ) as retry_controller:
            groups = client.groups.list(
                filter=f"startswith(displayName, '{group_name}')"
            )
            async for g in groups:
                if g.display_name == group_name:
                    group = g
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

    members = []
    async with GlobalRetryController(
        fn_identifier="azure_ad.list_group_members"
    ) as retry_controller:
        members_list = client.group_members.list(group_id)
        async for member in members_list:
            m = client.users.get(member.id)
            members.append(
                User(
                    user_id=m.object_id,
                    idp_name=azure_ad_organization.idp_name,
                    username=m.user_principal_name,
                    status=m.account_enabled,
                    extra={},
                    profile={
                        "first_name": m.given_name,
                        "last_name": m.surname,
                        "email": m.mail,
                        "phone_number": m.mobile,
                    },
                )
            )
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
    client: msal.ClientApplication,
    context: ExecutionContext,
) -> Optional[Group]:
    """
    Create a new group in Azure AD.
    Args:
    - group_name: The name of the group to create.
    - idp_name: The IDP name for the group.
    - description: The description for the group.
    - client: An instance of the msal.ClientApplication class, which provides access to the Azure AD API.
    - context: The execution context for the operation.

    Returns:
    - An instance of the `Group` class, representing the created group. If an error occurs, returns None.
    """

    # TODO: Need ProposedChanges, support context.execute = False
    if context.execute:
        graph_endpoint = "https://graph.windows.net/{idp_name}/groups"
        scopes = ["Directory.AccessAsUser.All"]
        result = await client.acquire_token_silent(scopes, account=None)
        if "access_token" in result:
            access_token = result["access_token"]
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            group_data = {
                "displayName": group_name,
                "mailEnabled": False,
                "mailNickname": group_name,
                "securityEnabled": True,
                "description": description,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    graph_endpoint, headers=headers, json=group_data
                ) as response:
                    if response.status == 201:
                        group = await response.json()
                        return Group(
                            idp_name=idp_name,
                            name=group_name,
                            description=description,
                            group_id=group["objectId"],
                            attributes=dict(),
                        )
                    else:
                        log.error("Error creating group")
                        return None
        else:
            log.error("Could not get an access token")
            return None
    return None


async def update_group_name(
    group: Group,
    new_name: str,
    azure_ad_organization: AzureADOrganization,
    log_params: dict[str, str],
    context: ExecutionContext,
) -> List[ProposedChange]:
    """
    Update the name of a group in Azure AD.
        Args:
        group (Group): The group to update the name of.
        new_name (str): The new name for the group.
        azure_ad_organization (AzureADOrganization): The Azure AD organization to update the group in.
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
    if context.execute:
        graph_client = azure_ad_organization.get_graph_client()
        try:
            group_update = (
                graph_client.groups.update(
                    group.group_id, display_name=new_name, description=group.description
                )
                .response()
                .result()
            )
            group.name = group_update["display_name"]
        except Exception as error:
            raise Exception("Error updating group: {}".format(str(error)))
    return response


async def update_group_description(
    group: Group,
    new_description: str,
    azure_ad_organization: AzureADOrganization,
    log_params: dict[str, str],
    context: ExecutionContext,
) -> List[ProposedChange]:
    """
    Update the description of a group in Azure AD.

    Args:
        group (Group): The group to update the description of.
        new_description (str): The new description for the group.
        azure_ad_organization (AzureADOrganization): The Azure AD organization to update the group in.
        log_params (dict): Logging parameters.
        context (ExecutionContext): The context object containing the execution flag.

    Returns:
        List[ProposedChange]: A list of proposed changes to be applied.
    """
    response: list[ProposedChange] = []
    if group.description == new_description:
        return response
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
        client = await azure_ad_organization.get_client()
        try:
            group_obj = client.groups.get(group.group_id)
            group_obj.description = new_description
            group_obj.update()
        except Exception as e:
            raise Exception("Error updating group description") from e
    return response


async def update_group_members(
    group: Group,
    new_members: List[UserSimple],
    azure_ad_organization: AzureADOrganization,
    context: ExecutionContext,
) -> List[ProposedChange]:
    """
    Update the members of a group in Azure AD.

    Args:
        group (Group): The group to update the members of.
        new_members (List[UserSimple]): The new members to add to the group.
        azure_ad_organization (AzureADOrganization): The Azure AD organization to update the group in.
        context (ExecutionContext): The context object containing the execution flag.

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

    if context.execute:
        graph_client = await azure_ad_organization.get_graph_client()

        for member_id in members_to_remove:
            try:
                await graph_client.groups.remove_member(group.group_id, member_id)
            except GraphError as e:
                log.error(
                    "Error removing member from group",
                    group=group.name,
                    member=member_id,
                    error=str(e),
                )
                continue

        for member_id in members_to_add:
            try:
                await graph_client.groups.add_member(group.group_id, member_id)
            except GraphError as e:
                log.error(
                    "Error adding member to group",
                    group=group.name,
                    member=member_id,
                    error=str(e),
                )
                continue
    return response


async def maybe_delete_group(
    delete: bool,
    group: Group,
    azure_ad_organization: AzureADOrganization,
    log_params: dict[str, str],
    context: ExecutionContext,
) -> List[ProposedChange]:
    """
    Delete a group in Azure AD.
    Args:
        delete (bool): Whether to delete the group.
        group (Group): The group to delete.
        azure_ad_organization (AzureADOrganization): The Azure AD organization to delete the group from.
        log_params (dict): Logging parameters.
        context (ExecutionContext): The context object containing the execution flag.

    Returns:
        List[ProposedChange]: A list of proposed changes to be applied.
    """

    response: list[ProposedChange] = []
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
        graph_client = await azure_ad_organization.get_graph_client()
        try:
            await graph_client.groups.delete(group.group_id)
        except GraphError as error:
            log.error(f"Error deleting group: {error}", **log_params)
            raise Exception("Error deleting group")

    return response
