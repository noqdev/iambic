from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.error import HTTPError

from googleapiclient import _auth

from iambic.core.context import ctx
from iambic.core.logger import log
from iambic.core.models import ProposedChange, ProposedChangeType
from iambic.core.utils import aio_wrapper
from iambic.plugins.v0_1_0.google_workspace.user.models import (
    GoogleWorkspaceUserTemplate,
)

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.google_workspace.iambic_plugin import GoogleProject


# https://googleapis.github.io/google-api-python-client/docs/dyn/admin_directory_v1.users.html
async def list_users(
    domain: str, google_project: GoogleProject
) -> list[GoogleWorkspaceUserTemplate]:
    from iambic.plugins.v0_1_0.google_workspace.user.models import get_user_template

    users = []
    try:
        service = await google_project.get_service_connection(
            "admin", "directory_v1", domain
        )
        if not service:
            return []
        http = _auth.authorized_http(service._http.credentials)
    except AttributeError as err:
        log.exception("Unable to process google users.", error=err)
        raise

    req = await aio_wrapper(service.users().list, domain=domain)
    while req is not None:
        res = req.execute(http=http)
        if res and "users" in res:
            for user in res["users"]:
                user_template = await get_user_template(service, user, domain)
                users.append(user_template)

        # handle pagination based on https://googleapis.github.io/google-api-python-client/docs/pagination.html
        req = await aio_wrapper(service.users().list_next, req, res)
    return users


async def get_user(user_email: str, domain: str, google_project: GoogleProject):
    from iambic.plugins.v0_1_0.google_workspace.user.models import (
        get_user_template,  # Adjust import based on your setup
    )

    try:
        service = await google_project.get_service_connection(
            "admin", "directory_v1", domain
        )
        if not service:
            return []
        http = _auth.authorized_http(service._http.credentials)
    except AttributeError as err:
        log.exception("Unable to process google users.", error=err)
        return

    req = service.users().get(userKey=user_email)
    try:
        if user := req.execute(http=http):
            return await get_user_template(service, user, domain)
    except HTTPError as err:
        log.error("Unable to get user. It may not exist", error=err.reason)


async def create_user(
    primary_email: str, name: dict, domain: str, google_project: GoogleProject
):
    try:
        service = await google_project.get_service_connection(
            "admin", "directory_v1", domain
        )
        if not service:
            return []
        http = _auth.authorized_http(service._http.credentials)
    except AttributeError as err:
        log.exception("Unable to process google users.", error=err)
        return

    body = {"primaryEmail": primary_email, "name": name}

    req = await aio_wrapper(
        service.users().insert,
        body=body,
    )
    return req.execute(http=http)


async def update_user_email(
    current_email: str, proposed_email: str, log_params: dict[str, str]
) -> list[ProposedChange]:
    response: list[ProposedChange] = []
    if current_email == proposed_email:
        return response

    log_str = "Detected updated user email"
    response.append(
        ProposedChange(
            change_type=ProposedChangeType.UPDATE,
            resource_id=current_email,
            resource_type="google:user:template",
            attribute="email",
            change_summary={
                "current_email": current_email,
                "proposed_email": proposed_email,
            },
            current_value=current_email,
            new_value=proposed_email,
        )
    )
    if ctx.execute:
        log_str = "Updating user email"
        # Update user email logic
    log.info(
        log_str,
        current_email=current_email,
        proposed_email=proposed_email,
        **log_params,
    )
    return response


async def maybe_delete_user(
    user: GoogleWorkspaceUserTemplate,
    google_project: GoogleProject,
    log_params: dict[str, str],
) -> list[ProposedChange]:
    response: list[ProposedChange] = []

    # If the user is not marked for deletion, return an empty response.
    if not user.deleted:
        return response

    # Create a proposed change object indicating that the user should be deleted.
    response.append(
        ProposedChange(
            change_type=ProposedChangeType.DELETE,
            resource_id=user.properties.primary_email,
            resource_type=user.resource_type,
            attribute="user",
            change_summary={"user": user.properties.name},
            current_value=user.properties.name,
        )
    )

    # If execution is enabled, proceed to delete the user.
    if ctx.execute:
        try:
            service = await google_project.get_service_connection(
                "admin", "directory_v1", user.properties.domain
            )
            if not service:
                return []
            http = _auth.authorized_http(service._http.credentials)
        except AttributeError as err:
            log.exception("Unable to process google users.", error=err)
            return []

        log_str = "Detected user deletion"

        if ctx.execute:
            log_str = "Deleting User"
            await aio_wrapper(
                service.users().delete(userKey=user.properties.primary_email).execute,
                http=http,
            )
        log.info(log_str, user_email=user.properties.primary_email, **log_params)
    return response


async def update_user_name(
    user_email: str,
    current_name: dict,
    proposed_name: dict,
    domain: str,
    google_project: GoogleProject,
    log_params: dict[str, str],
) -> list[ProposedChange]:
    response: list[ProposedChange] = []

    # Check if the current name and proposed name are the same.
    if current_name == proposed_name:
        return response

    # Log and record a proposed change if the names differ.
    log_str = "Detected user name update"
    response.append(
        ProposedChange(
            change_type=ProposedChangeType.UPDATE,
            resource_id=user_email,
            resource_type="google:user:template",
            attribute="user_name",
            current_value=current_name,
            new_value=proposed_name,
        )
    )

    # Connect to the Google service.
    try:
        service = await google_project.get_service_connection(
            "admin", "directory_v1", domain
        )
        if not service:
            return response
        http = _auth.authorized_http(service._http.credentials)
    except AttributeError as err:
        log.exception("Unable to process google users.", error=err)
        return response

    # If execution is enabled, update the user's name.
    if ctx.execute:
        log_str = "Updating user name"
        await aio_wrapper(
            service.users()
            .patch(userKey=user_email, body={"name": proposed_name})
            .execute,
            http=http,
        )

    log.info(
        log_str, current_name=current_name, proposed_name=proposed_name, **log_params
    )

    return response
