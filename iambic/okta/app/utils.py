from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, List, Optional

import okta.models as models

from iambic.config.models import OktaOrganization
from iambic.core.context import ExecutionContext
from iambic.core.logger import log
from iambic.core.models import ProposedChange, ProposedChangeType
from iambic.okta.app.models import OktaAppTemplate
from iambic.okta.models import App, Assignment, User

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


async def list_app_user_assignments(
    okta_organization: OktaOrganization, app: App
) -> dict:
    client = await okta_organization.get_okta_client()
    app_user_list, _, err = await client.list_application_users(app.id)
    if err:
        log.error("Error encountered when listing app users", error=str(err))

    user_assignments = []
    for user in app_user_list:
        user_okta, _, err = await client.get_user(user.id)
        if err:
            log.error("Error encountered when getting user", error=str(err))
            raise Exception("Error encountered when getting user")
        user_assignments.append(user_okta.profile.login)

    return {
        "app_id": app.id,
        "user_assignments": user_assignments,
    }


async def get_app(okta_organization: OktaOrganization, app_id: str) -> App:
    client = await okta_organization.get_okta_client()
    app_raw, _, err = await client.get_application(app_id)
    if err:
        log.error("Error encountered when getting app", error=str(err))
        raise Exception("Error encountered when getting app")

    app = App(
        id=app_raw.id,
        idp_name=okta_organization.idp_name,
        name=app_raw.label,
        app_id=app_raw.id,
        attributes=dict(),
        extra=dict(
            okta_app_id=app_raw.id,
            created=app_raw.created,
        ),
    )

    user_assignments = await list_app_user_assignments(okta_organization, app)
    group_assignments = await list_app_group_assignments(okta_organization, app)
    for assignment in user_assignments:
        for user_assignment in assignment.get("user_assignments", []):
            app.assignments.append(Assignment(user=user_assignment))
    for assignment in group_assignments:
        for group_assignment in assignment.get("group_assignments", []):
            app.assignments.append(Assignment(group=group_assignment))
    return app


async def list_app_group_assignments(
    okta_organization: OktaOrganization, app: App
) -> dict:
    client = await okta_organization.get_okta_client()
    app_group_assignments, _, err = await client.list_application_group_assignments(
        app.id
    )
    if err:
        log.error(
            "Error encountered when listing app group assignments", error=str(err)
        )
    groups_assignments = []
    for assignment in app_group_assignments:
        group, resp, err = await client.get_group(assignment.id)
        if err:
            log.error(
                "Error encountered when getting group",
                group_id=assignment.id,
                error=str(err),
            )
            continue
        groups_assignments.append(group.profile.name)
    return {
        "app_id": app.id,
        "group_assignments": groups_assignments,
    }


async def get_app_profile_mapping(okta_organization: OktaOrganization, app):
    client = await okta_organization.get_okta_client()
    # https://dev-876967-admin.okta.com/api/v1/apps/user/types/oty83zftta0RI9XV54x7/schemas
    # mappings: [{"sourceId":"oty83zftta0RI9XV54x7","targetId":"otyate20a01jh8z5C4x6","propertyMappings":[{"targetField":"firstName","sourceExpression":"appuser.firstName","pushStatus":"DONT_PUSH"},{"targetField":"lastName","sourceExpression":"appuser.lastName","pushStatus":"DONT_PUSH"},{"targetField":"mobilePhone","sourceExpression":"appuser.mobilePhone","pushStatus":"DONT_PUSH"},{"targetField":"secondEmail","sourceExpression":"appuser.secondEmail","pushStatus":"DONT_PUSH"},{"targetField":"email","sourceExpression":"appuser.email","pushStatus":"DONT_PUSH"}]}]
    # get_profile_mapping(
    # self, mappingId,
    # keep_empty_params=False

    #     Enumerates Profile Mappings in your organization with p
    # agination.
    # Args:
    #     query_params {dict}: Map of query parameters for request
    #     [query_params.after] {str}
    #     [query_params.limit] {str}
    #     [query_params.sourceId] {str}
    #     [query_params.targetId] {str}
    profile_mappings, _, err = await client.list_profile_mappings({})
    if err:
        log.error(
            "Error encountered when listing app group assignments", error=str(err)
        )
        raise Exception("Error encountered when listing app group assignments")

    return {
        "app_id": app.id,
        "profile_mappings": profile_mappings,
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
    raw_apps, resp, err = await client.list_applications()
    if err:
        log.error("Error encountered when listing apps", error=str(err))
        raise Exception("Error encountered when listing apps")
    while resp.has_next():
        next_apps, resp, err = await client.list_applications()
        if err:
            log.error("Error encountered when listing apps", error=str(err))
            return []
        raw_apps.append(next_apps)
    tasks = []
    apps = []

    for app_raw in raw_apps:
        app = App(
            id=app_raw.id,
            idp_name=okta_organization.idp_name,
            name=app_raw.label,
            app_id=app_raw.id,
            attributes=dict(),
            status=app_raw.status,
            extra=dict(
                okta_app_id=app_raw.id,
                created=app_raw.created,
            ),
        )
        apps.append(app)
        tasks.append(list_app_user_assignments(okta_organization, app))
        tasks.append(list_app_group_assignments(okta_organization, app))
        tasks.append(get_app_profile_mapping(okta_organization, app))
    app_assignments = await asyncio.gather(*tasks)
    apps_to_return = []
    for app in apps:
        assignments = [a for a in app_assignments if a["app_id"] == app.id]
        for assignment in assignments:
            for user_assignment in assignment.get("user_assignments", []):
                app.assignments.append(Assignment(user=user_assignment))
            for group_assignment in assignment.get("group_assignments", []):
                app.assignments.append(Assignment(group=group_assignment))
            for profile_mappings in assignment.get("profile_mappings", []):
                app.profile_mappings = profile_mappings
        apps_to_return.append(app)
    return apps_to_return


async def update_app_assignments(
    app: App,
    new_assignments: List[Assignment],
    okta_organization: OktaOrganization,
    log_params: dict[str, str],
    context: ExecutionContext,
) -> List[ProposedChange]:
    """
    Update the assignments of a app in Okta.

    Args:
        app (App): The app to update the assignments of.
        new_assignments (List[Assignment]): The new assignments to add to the app.
        okta_organization (OktaOrganization): The Okta organization to update the app in.
        log_params (dict): Logging parameters.
        context (object): The context object containing the execution flag.

    Returns:
        List[ProposedChange]: A list of proposed changes to be applied.
    """
    client = await okta_organization.get_okta_client()
    response = []
    current_assignments = app.assignments
    desired_assignments = new_assignments
    assignments_to_unassign = [
        assignment
        for assignment in current_assignments
        if assignment not in desired_assignments
    ]

    assignments_to_assign = [
        assignment
        for assignment in desired_assignments
        if assignment not in current_assignments
    ]

    if assignments_to_unassign:
        response.append(
            ProposedChange(
                change_type=ProposedChangeType.DETACH,
                resource_id=app.app_id,
                resource_type=app.resource_type,
                attribute="assignments",
                change_summary={"AssignmentsToUnassign": list(assignments_to_unassign)},
            )
        )

    if assignments_to_assign:
        response.append(
            ProposedChange(
                change_type=ProposedChangeType.ATTACH,
                resource_id=app.app_id,
                resource_type=app.resource_type,
                attribute="assignments",
                change_summary={"AssignmentsToAssign": list(assignments_to_assign)},
            )
        )

    if context.execute:
        for assignment in assignments_to_assign:
            if assignment.user:
                user_okta, _, err = await client.get_user(assignment.user)
                if err:
                    log.error(
                        "Error retrieving user", user=assignment.user, **log_params
                    )
                    continue
                _, err = await client.assign_user_to_application(
                    user_okta.id, app.extra["okta_app_id"]
                )
                if err:
                    log.error(
                        "Error assigning user to app",
                        user=assignment.user,
                        **log_params,
                    )
                    continue
            elif assignment.group:
                group_okta, _, err = await client.get_group(assignment.group)
                if err:
                    log.error(
                        "Error retrieving group", group=assignment.group, **log_params
                    )
                    continue
                _, err = await client.assign_group_to_application(
                    group_okta.id, app.extra["okta_app_id"]
                )
                if err:
                    log.error(
                        "Error assigning group to app",
                        group=assignment.group,
                        **log_params,
                    )
                    continue

    return response


async def create_app(
    app: OktaAppTemplate, okta_organization: OktaOrganization, context: ExecutionContext
):
    client = await okta_organization.get_okta_client()
    app_data = app.dict()
    app_data.pop("template_type", None)
    app_data.pop("properties", None)
    app_data["name"] = app.properties.name
    app_data["id"] = app.properties.id
    app_data["description"] = app.properties.description
    app_data["extra"] = app.properties.extra
    app_data["created"] = app.properties.created
    app_data["assignments"] = app.properties.assignments

    if context.execute:
        new_app, _, err = await client.create_application(app_data)
        if err:
            raise ValueError(f"Error creating Okta app: {err}")
        return new_app
    else:
        return ProposedChange(
            change_type=ProposedChangeType.CREATE,
            resource_type=app.resource_type,
            resource_id=app.resource_id,
            attribute="app",
            change_summary=app_data,
        )
