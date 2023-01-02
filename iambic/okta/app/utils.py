from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, List, Optional

import okta.models as models

from iambic.config.models import OktaOrganization
from iambic.core.context import ExecutionContext
from iambic.core.logger import log
from iambic.core.models import ProposedChange, ProposedChangeType
from iambic.okta.models import App, User

if TYPE_CHECKING:
    from iambic.okta.group.models import UserSimple


async def list_all_apps(okta_organization: OktaOrganization) -> List[App]:
    """
    List all apps in Okta.

    Args:
    - okta_organization: An instance of the OktaOrganization class, which provides access to the Okta API.

    Returns:
    - A list of `App` instances, representing the apps in Okta.
    """

    client = await okta_organization.get_okta_client()
    apps, resp, err = await client.list_applications()
    while resp.has_next():
        next_apps, resp, err = await client.list_applications()
        if err:
            log.error("Error encountered when listing apps", error=str(err))
            return []
        apps.append(next_apps)

    tasks = []
    apps_to_return = []
    # for app_raw in apps:
    #     app = App(
    #         idp_name=okta_organization.idp_name,
    #         name=app_raw.label,
    #         app_id=app_raw.id,
    #         attributes=dict(),
    #         extra=dict(
    #             okta_app_id=app_raw.id,
    #             created=app_raw.created,
    #         ),
    #     )
    #     tasks.append(list_app_users(app, okta_organization))
    apps_to_return = await asyncio.gather(*tasks)
    return apps_to_return
