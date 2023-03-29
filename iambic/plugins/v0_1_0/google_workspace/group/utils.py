from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from googleapiclient import _auth
from googleapiclient.errors import HttpError

from iambic.core.context import ctx
from iambic.core.logger import log
from iambic.core.models import ProposedChange, ProposedChangeType
from iambic.core.utils import aio_wrapper

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.google_workspace.group.models import (
        GoogleWorkspaceGroupTemplate,
        GroupMember,
    )
    from iambic.plugins.v0_1_0.google_workspace.iambic_plugin import GoogleProject


async def list_groups(
    domain: str, google_project: GoogleProject
) -> list[GoogleWorkspaceGroupTemplate]:
    from iambic.plugins.v0_1_0.google_workspace.group.models import get_group_template

    groups = []
    try:
        service = await google_project.get_service_connection(
            "admin", "directory_v1", domain
        )
        if not service:
            return []
        http = _auth.authorized_http(service._http.credentials)
    except AttributeError as err:
        log.exception("Unable to process google groups.", error=err)
        raise

    req = await aio_wrapper(service.groups().list, domain=domain)
    res = req.execute(http=http)
    if res and "groups" in res:
        for group in res["groups"]:
            group_template = await get_group_template(service, group, domain)
            groups.append(group_template)
    return groups


async def get_group(group_email: str, domain: str, google_project: GoogleProject):
    from iambic.plugins.v0_1_0.google_workspace.group.models import get_group_template

    try:
        service = await google_project.get_service_connection(
            "admin", "directory_v1", domain
        )
        if not service:
            return []
        http = _auth.authorized_http(service._http.credentials)
    except AttributeError as err:
        log.exception("Unable to process google groups.", error=err)
        return

    # TODO: Error handling:
    req = service.groups().get(groupKey=group_email)
    try:
        if group := req.execute(http=http):
            return await get_group_template(service, group, domain)
    except HttpError as err:
        if err.reason == "Not Authorized to access this resource/api":
            log.error("Unable to get group. It may not exist", error=err.reason)
        else:
            raise


async def create_group(
    id: str,
    domain: str,
    email: str,
    name: str,
    description: str,
    google_project: GoogleProject,
):
    try:
        service = await google_project.get_service_connection(
            "admin", "directory_v1", domain
        )
        if not service:
            return []
        http = _auth.authorized_http(service._http.credentials)
    except AttributeError as err:
        log.exception("Unable to process google groups.", error=err)
        return
    req = await aio_wrapper(
        service.groups().insert,
        body={"id": id, "email": email, "name": name, "description": description},
    )
    return req.execute(http=http)


async def update_group_domain(
    current_domain: str, proposed_domain: str, log_params: dict[str, str]
):
    response = []
    if current_domain != proposed_domain:
        log_str = "Modifying group domain"
        response.append(
            ProposedChange(
                change_type=ProposedChangeType.UPDATE,
                attribute="domain",
                change_summary={
                    "current_domain": current_domain,
                    "proposed_domain": proposed_domain,
                },
                current_value=current_domain,
                new_value=proposed_domain,
            )
        )
        log.info(
            log_str,
            current_domain=current_domain,
            proposed_domain=proposed_domain,
            **log_params,
        )
        raise NotImplementedError(
            f"Current Domain {current_domain} does not match "
            f"proposed domain {proposed_domain}. We are unable "
            "to update group domains at this point in time."
        )
    return response


async def update_group_description(
    group_email,
    current_description,
    proposed_description,
    domain: str,
    google_project: GoogleProject,
    log_params: dict[str, str],
) -> list[ProposedChange]:
    response: list[ProposedChange] = []
    if current_description == proposed_description:
        return response
    try:
        service = await google_project.get_service_connection(
            "admin", "directory_v1", domain
        )
        if not service:
            return response
        http = _auth.authorized_http(service._http.credentials)
    except AttributeError as err:
        log.exception("Unable to process google groups.", error=err)
        return response
    log_str = "Detected updated group description"
    response.append(
        ProposedChange(
            change_type=ProposedChangeType.UPDATE,
            resource_id=group_email,
            resource_type="google:group:template",
            attribute="description",
            change_summary={
                "current_description": current_description,
                "proposed_description": proposed_description,
            },
            current_value=current_description,
            new_value=proposed_description,
        )
    )
    if ctx.execute:
        log_str = "Updating group description"
        await aio_wrapper(
            service.groups()
            .patch(groupKey=group_email, body={"description": proposed_description})
            .execute,
            http=http,
        )
    log.info(
        log_str,
        current_description=current_description,
        proposed_description=proposed_description,
        **log_params,
    )
    return response


async def update_group_name(
    group_email: str,
    current_name: str,
    proposed_name: str,
    domain: str,
    google_project: GoogleProject,
    log_params: dict[str, str],
) -> list[ProposedChange]:
    response: list[ProposedChange] = []
    if current_name == proposed_name:
        return response
    log_str = "Detected group name update"
    response.append(
        ProposedChange(
            change_type=ProposedChangeType.UPDATE,
            resource_id=group_email,
            resource_type="google:group:template",
            attribute="group_name",
            current_value=current_name,
            new_value=proposed_name,
        )
    )

    try:
        service = await google_project.get_service_connection(
            "admin", "directory_v1", domain
        )
        if not service:
            return response
        http = _auth.authorized_http(service._http.credentials)
    except AttributeError as err:
        log.exception("Unable to process google groups.", error=err)
        return response
    if ctx.execute:
        log_str = "Updating group name"
        await aio_wrapper(
            service.groups()
            .patch(groupKey=group_email, body={"name": proposed_name})
            .execute,
            http=http,
        )
    log.info(
        log_str, current_name=current_name, proposed_name=proposed_name, **log_params
    )
    return response


async def update_group_email(
    current_email: str,
    proposed_email: str,
    domain: str,
    google_project: GoogleProject,
    log_params: dict[str, str],
) -> list[ProposedChange]:
    # TODO: This won't work as-is, since we aren't really aware of the old e-mail
    response: list[ProposedChange] = []
    if current_email == proposed_email:
        return response
    log_str = "Detected group e-mail update"
    response.append(
        ProposedChange(
            change_type=ProposedChangeType.UPDATE,
            resource_id=current_email,
            resource_type="google:group:template",
            attribute="group_email",
            current_value=current_email,
            new_value=proposed_email,
        )
    )

    try:
        service = await google_project.get_service_connection(
            "admin", "directory_v1", domain
        )
        if not service:
            return response
        http = _auth.authorized_http(service._http.credentials)
    except AttributeError as err:
        log.exception("Unable to process google groups.", error=err)
        return response
    if ctx.execute:
        log_str = "Updating group e-mail"
        await aio_wrapper(
            service.groups()
            .patch(groupKey=current_email, body={"email": proposed_email})
            .execute,
            http=http,
        )
    log.info(
        log_str, current_name=current_email, proposed_name=proposed_email, **log_params
    )
    return response


async def maybe_delete_group(
    group: GoogleWorkspaceGroupTemplate,
    google_project: GoogleProject,
    log_params: dict[str, str],
) -> list[ProposedChange]:
    response: list[ProposedChange] = []
    if not group.deleted:
        return response
    response.append(
        ProposedChange(
            change_type=ProposedChangeType.DELETE,
            resource_id=group.properties.email,
            resource_type=group.resource_type,
            attribute="group",
            change_summary={"group": group.properties.name},
            current_value=group.properties.name,
        )
    )
    if ctx.execute:
        try:
            service = await google_project.get_service_connection(
                "admin", "directory_v1", group.properties.domain
            )
            if not service:
                return []
            http = _auth.authorized_http(service._http.credentials)
        except AttributeError as err:
            log.exception("Unable to process google groups.", error=err)
            return []

        log_str = "Detected group deletion"

        if ctx.execute:
            log_str = "Deleting Group"
            await aio_wrapper(
                service.groups().delete(groupKey=group.properties.email).execute,
                http=http,
            )
        log.info(log_str, group_email=group.properties.email, **log_params)
    return response


async def get_group_members(service, group):
    from iambic.plugins.v0_1_0.google_workspace.group.models import (
        GroupMember,
        GroupMemberRole,
        GroupMemberStatus,
        GroupMemberType,
    )

    http = _auth.authorized_http(service._http.credentials)
    member_req = service.members().list(groupKey=group["email"])
    member_res = member_req.execute(http=http) or {}
    return [
        GroupMember(
            email=member["email"],
            role=GroupMemberRole(member["role"]),
            type=GroupMemberType(member["type"]),
            status=GroupMemberStatus(member.get("status", GroupMemberStatus.UNDEFINED)),
        )
        for member in member_res.get("members", [])
    ]


async def update_group_members(
    group_email: str,
    current_members: list[GroupMember],
    proposed_members: list[GroupMember],
    domain: str,
    google_project: GoogleProject,
    log_params: dict[str, str],
):
    # TODO: This will likely fail if I change the Role of a user, since we are doing all
    # of these operations with asyncio.gather. Should do the remove operations first, then the add ones.
    tasks = []
    response = []
    try:
        service = await google_project.get_service_connection(
            "admin", "directory_v1", domain
        )
        if not service:
            return False
    except AttributeError as err:
        log.exception("Unable to process google groups.", error=err)
        return

    if users_to_remove := [
        member
        for member in current_members
        if member.email not in [m.email for m in proposed_members]
    ]:
        log_str = "Detected users to remove from group"
        response.append(
            ProposedChange(
                change_type=ProposedChangeType.DETACH,
                resource_id=group_email,
                resource_type="google:group:template",
                attribute="users",
                change_summary={
                    "UsersToRemove": [user.email for user in users_to_remove]
                },
                current_value=[user.email for user in current_members],
                new_value=[user.email for user in proposed_members],
            )
        )
        if ctx.execute:
            log_str = "Removing users from group"
            for user in users_to_remove:
                http = _auth.authorized_http(service._http.credentials)
                tasks.append(
                    aio_wrapper(
                        service.members()
                        .delete(groupKey=group_email, memberKey=user.email)
                        .execute,
                        http=http,
                    )
                )
        log.info(log_str, users=[user.email for user in users_to_remove], **log_params)

    if users_to_add := [
        member
        for member in proposed_members
        if member.email not in [m.email for m in current_members]
    ]:
        log_str = "Detected new users to add to group"
        response.append(
            ProposedChange(
                change_type=ProposedChangeType.ATTACH,
                resource_id=group_email,
                resource_type="google:group:template",
                attribute="users",
                change_summary={"UsersToAdd": [user.email for user in users_to_add]},
                current_value=[user.email for user in current_members],
                new_value=[user.email for user in proposed_members],
            )
        )
        if ctx.execute:
            log_str = "Adding users to group"
            for user in users_to_add:
                http = _auth.authorized_http(service._http.credentials)
                tasks.append(
                    aio_wrapper(
                        service.members()
                        .insert(
                            groupKey=group_email,
                            body={
                                "email": user.email,
                                "role": user.role.value,
                                "type": user.type.value,
                                "status": user.status.value,
                            },
                        )
                        .execute,
                        http=http,
                    )
                )

        log.info(log_str, users=[user.email for user in users_to_add], **log_params)
    if tasks:
        await asyncio.gather(*tasks)
    return response
