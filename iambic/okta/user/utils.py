from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import okta.models as models
from okta.models import User

from iambic.config.models import OktaOrganization
from iambic.core.context import ExecutionContext
from iambic.core.logger import log
from iambic.core.models import ProposedChange, ProposedChangeType
from iambic.okta.models import User

log = logging.getLogger(__name__)


async def create_user(
    username: str,
    attributes: Dict[str, Any],
    okta_organization: OktaOrganization,
    context: ExecutionContext,
) -> Optional[User]:
    """
    Create a new user in Okta.

    Args:
        username (str): The username of the user to create.
        attributes (Dict[str, Any]): The attributes for the user.
        okta_organization (OktaOrganization): The Okta organization to create the user in.

    Returns:
        User: The created User object.
    """

    # TODO: Need ProposedChanges, support context.execute = False
    client = await okta_organization.get_okta_client()

    user_profile = models.UserProfile(attributes)
    user_profile.login = username

    # Create the user
    user_model = models.User({"profile": user_profile})
    if context.execute:
        user, resp, err = await client.create_user(user_model)
        if err:
            raise Exception("Error creating user")
        user = User(
            idp_name=okta_organization.idp_name,
            username=username,
            attributes=attributes,
            status=user.status,
            extra=dict(
                okta_user_id=user.id,
                created=user.created,
            ),
        )
        return user
    return None


async def get_user(
    username: str,
    okta_organization: OktaOrganization,
) -> Optional[User]:
    """
    Retrieve a user from Okta by username.

    Args:
        username (str): The username of the user to retrieve.
        okta_organization (OktaOrganization): The Okta organization to retrieve the user from.

    Returns:
        User: The retrieved User object.
    """

    client = await okta_organization.get_okta_client()
    user, _, err = await client.get_user(username)
    if err:
        raise Exception(f"Error retrieving user: {err}")
    return User(
        idp_name=okta_organization.idp_name,
        username=user.profile.login,
        attributes=user.profile,
        status=user.status,
        extra=dict(
            okta_user_id=user.id,
            created=user.created,
        ),
    )


async def change_user_status(
    user: User,
    new_status: str,
    okta_organization: OktaOrganization,
    context: ExecutionContext,
) -> List[ProposedChange]:
    """
    Change a user's status in Okta.

    Args:
        user (User): The user to change the status of.
        new_status (str): The new status for the user.
        okta_organization (OktaOrganization): The Okta organization to change the user in.
        context (ExecutionContext): The context object containing the execution flag.

    Returns:
        List[ProposedChange]: A list of proposed changes to be applied.
    """

    client = await okta_organization.get_okta_client()
    response: list = []

    if user.status == new_status:
        return response

    response.append(
        ProposedChange(
            change_type=ProposedChangeType.UPDATE,
            resource_id=user.user_id,
            resource_type=user.resource_type,
            attribute="status",
            new_value=new_status,
        )
    )

    if context.execute:
        updated_user, resp, err = await client.update_user(
            user.extra["okta_user_id"],
            {"status": new_status},
        )
        if err:
            raise Exception("Error updating user status")
        user.status = updated_user.status
    return response


async def update_user_status(
    user: User,
    new_status: str,
    okta_organization: OktaOrganization,
    log_params: dict[str, str],
    context: ExecutionContext,
) -> List[ProposedChange]:
    """
    Update the status of a user in Okta.

    Args:
        user (User): The user to update the status of.
        new_status (str): The new status for the user.
        okta_organization (OktaOrganization): The Okta organization to update the user in.
        log_params (dict): Logging parameters.
        context (ExecutionContext): The context object containing the execution flag.

    Returns:
        List[ProposedChange]: A list of proposed changes to be applied.
    """
    client = await okta_organization.get_okta_client()
    response: list = []
    if user.status == new_status:
        return response
    response.append(
        ProposedChange(
            change_type=ProposedChangeType.UPDATE,
            resource_id=user.user_id,
            resource_type=user.resource_type,
            attribute="status",
            change_summary={
                "current_status": user.status,
                "proposed_status": new_status,
            },
        )
    )
    if context.execute:
        _, err = await client.update_user_status(user.user_id, new_status)
        if err:
            log.error(
                "Error updating user status",
                user=user.username,
                status=new_status,
                **log_params,
            )
    return response


async def update_user_attribute(
    user: User,
    new_value: str,
    attribute_name: str,
    okta_organization: OktaOrganization,
    log_params: dict[str, str],
    context: ExecutionContext,
) -> List[ProposedChange]:
    """
    Update an attribute of a user in Okta.

    Args:
        user (User): The user to update the attribute of.
        new_value (str): The new value for the attribute.
        attribute_name (str): The name of the attribute to update.
        okta_organization (OktaOrganization): The Okta organization to update the user in.
        log_params (dict): Logging parameters.
        context (ExecutionContext): The context object containing the execution flag.

    Returns:
        List[ProposedChange]: A list of proposed changes to be applied.
    """
    response: list = []
    if user.attributes[attribute_name] == new_value:
        return response
    response.append(
        ProposedChange(
            change_type=ProposedChangeType.UPDATE,
            resource_id=user.user_id,
            resource_type=user.resource_type,
            attribute=attribute_name,
            new_value=new_value,
        )
    )
    user_profile = models.UserProfile({attribute_name: new_value})
    user_model = models.User({"profile": user_profile})
    if context.execute:
        client = await okta_organization.get_okta_client()
        updated_user, resp, err = await client.update_user(
            user.extra["okta_user_id"], user_model
        )
        if err:
            raise Exception(f"Error updating user's {attribute_name}")
        user = User(
            idp_name=okta_organization.idp_name,
            username=updated_user.profile.login,
            email=updated_user.profile.email,
            status=updated_user.status,
            user_id=updated_user.id,
            attributes=updated_user.profile,
            extra=dict(
                okta_user_id=updated_user.id,
                created=updated_user.created,
            ),
        )
    return response


async def maybe_delete_user(
    delete: bool,
    user: User,
    okta_organization: OktaOrganization,
    log_params: dict[str, str],
    context: ExecutionContext,
) -> List[ProposedChange]:
    """
    Delete a user in Okta.

    Args:
        user (User): The user to delete.
        okta_organization (OktaOrganization): The Okta organization to delete the user from.
        log_params (dict): Logging parameters.
        context (ExecutionContext): The context object containing the execution flag.

    Returns:
        List[ProposedChange]: A list of proposed changes to be applied.
    """
    response: list[ProposedChange] = []
    client = await okta_organization.get_okta_client()
    if not delete:
        return response
    response.append(
        ProposedChange(
            change_type=ProposedChangeType.DELETE,
            resource_id=user.user_id,
            resource_type=user.resource_type,
            attribute="user",
            change_summary={"user": user.username},
        )
    )
    if context.execute:
        r, err = await client.deactivate_or_delete_user(user.extra["okta_user_id"])
        if err:
            raise Exception("Error deleting user")
    return response


async def update_user_assignments(
    user: User,
    new_assignments: List[str],
    okta_organization: OktaOrganization,
    log_params: dict[str, str],
    context: ExecutionContext,
) -> List[ProposedChange]:
    """
    Update the user's app assignments in Okta.

    Args:
        user (User): The user to update the app assignments of.
        new_assignments (List[str]): The new app assignments for the user.
        okta_organization (OktaOrganization): The Okta organization to update the user's app assignments in.
        log_params (dict): Logging parameters.
        context (ExecutionContext): The context object containing the execution flag.

    Returns:
        List[ProposedChange]: A list of proposed changes to be applied.
    """

    client = await okta_organization.get_okta_client()
    response = []
    current_assignments = [assignment.id for assignment in user.assignments]
    desired_assignments = new_assignments
    assignments_to_remove = [
        assignment
        for assignment in current_assignments
        if assignment not in desired_assignments
    ]
    assignments_to_add = [
        assignment
        for assignment in desired_assignments
        if assignment not in current_assignments
    ]

    if assignments_to_remove:
        response.append(
            ProposedChange(
                change_type=ProposedChangeType.DETACH,
                resource_id=user.user_id,
                resource_type=user.resource_type,
                attribute="assignments",
                change_summary={"AssignmentsToRemove": list(assignments_to_remove)},
            )
        )

    if assignments_to_add:
        response.append(
            ProposedChange(
                change_type=ProposedChangeType.ATTACH,
                resource_id=user.user_id,
                resource_type=user.resource_type,
                attribute="assignments",
                change_summary={"AssignmentsToAdd": list(assignments_to_add)},
            )
        )

    if context.execute:
        for assignment in assignments_to_remove:
            app, _, err = await client.get_app(assignment)
            if err:
                log.error("Error retrieving app", app=assignment, **log_params)
                continue
            _, err = await client.remove_user_from_app(user.id, app.id)
            if err:
                log.error(
                    "Error removing user from app",
                    user=user.username,
                    app=app.label,
                    **log_params,
                )
                continue
        for assignment in assignments_to_add:
            app_id, _, err = await client.get_application_by_label(assignment)
            if err:
                log.error(
                    "Error retrieving application",
                    application=assignment,
                    user=user.username,
                    **log_params,
                )
                continue
            _, err = await client.assign_application_to_user(user.id, app_id)
            if err:
                log.error(
                    "Error assigning application to user",
                    user=user.username,
                    application=assignment,
                    **log_params,
                )
                continue

        for assignment in assignments_to_remove:
            app_id, _, err = await client.get_application_by_label(assignment)
            if err:
                log.error(
                    "Error retrieving application",
                    application=assignment,
                    user=user.username,
                    **log_params,
                )
                continue
            _, err = await client.deassign_application_from_user(user.id, app_id)
            if err:
                log.error(
                    "Error deassigning application from user",
                    user=user.username,
                    application=assignment,
                    **log_params,
                )
                continue

        return response
