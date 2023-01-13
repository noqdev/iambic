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


# TODO:
# resp, _, err = await client.get_group_schema()
# resp, _, err = await client.update_group_schema(resp)
# resp, _, err = await client.update_application(resp)
# resp, _, err = await client.delete_application(resp)
# definition = {'custom':
#                 {'id': '#custom',
#                  'properties':
#                      {'testCustomAttr':
#                          {'description': 'Custom attribute for testing purposes',
#                                          'maxLength': 20,
#                                          'minLength': 1,
#                                          'permissions': [{'action': 'READ_WRITE',
#                                                           'principal': 'SELF'}],
#                                          'required': False,
#                                          'title': 'Test Custom Attribute',
#                                          'type': 'string'},
#                           'required': []},
#                  'type': 'object'
#                 }
#              }
# resp, _, err = await client.update_group_schema({'definitions': definition})
# await client.get_group_schema()

async def list_app_users(okta_organization: OktaOrganization, app: App) -> dict:
    client = await okta_organization.get_okta_client()
    app_user_list, _, err = await client.list_application_users(app.app_id)
    if err:
        log.error("Error encountered when listing app users", error=str(err))
    return {
        "app": app,
        "users": app_user_list,
    }



await def list_app_group_assignments(okta_organization: OktaOrganization, app: App) -> dict:
    client = await okta_organization.get_okta_client()
    app_group_assignments, _, err = await client.list_application_group_assignments(app.app_id)
    if err:
        log.error("Error encountered when listing app users", error=str(err))
    return {
        "app": app,
        "group_assignments": app_group_assignments,
    }

async def list_app_groups(okta_organization: OktaOrganization, app: App) -> list:
    client = await okta_organization.get_okta_client()
    app_user_list, _, err = await client.list_application_groups(app.app_id)
    if err:
        log.error("Error encountered when listing app users", error=str(err))
    return {
        "app": app,
        "users": app_user_list,
    }


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
    for app_raw in apps:
        app = App(
            idp_name=okta_organization.idp_name,
            name=app_raw.label,
            app_id=app_raw.id,
            attributes=dict(),
            extra=dict(
                okta_app_id=app_raw.id,
                created=app_raw.created,
            ),
        )
        tasks.append(list_app_users(okta_organization, app))
    apps_to_return = await asyncio.gather(*tasks)
    return apps_to_return
