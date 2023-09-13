from __future__ import annotations

from typing import TYPE_CHECKING

from googleapiclient import _auth

from iambic.core.logger import log
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
