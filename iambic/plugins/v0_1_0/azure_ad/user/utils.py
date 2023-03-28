from __future__ import annotations

import functools
import secrets
from typing import TYPE_CHECKING, List, Optional

from aiohttp import ClientResponseError

from iambic.core.context import ctx
from iambic.core.logger import log
from iambic.core.models import ProposedChange, ProposedChangeType
from iambic.core.utils import GlobalRetryController, snake_to_camelback
from iambic.plugins.v0_1_0.azure_ad.user.models import UserTemplateProperties

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.azure_ad.models import AzureADOrganization


async def list_users(
    azure_ad_organization: AzureADOrganization, **kwargs
) -> List[UserTemplateProperties]:
    """
    List all users in Azure AD.

    Args:
    - azure_ad_organization: An instance of the AzureADOrganization class, which provides access to the Azure AD API.

    Returns:
    - A list of `User` instances, representing the users in Azure AD.
    """

    async with GlobalRetryController(
        fn_identifier="azure_ad.list_users"
    ) as retry_controller:
        fn = functools.partial(azure_ad_organization.list, "users", **kwargs)
        users = await retry_controller(fn)

    return [UserTemplateProperties.from_azure_response(user) for user in users]


async def get_user(
    azure_ad_organization: AzureADOrganization,
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    allow_template_ref: bool = False,
) -> UserTemplateProperties:
    """
    Get Azure AD user.

    Args:
    - azure_ad_organization: An instance of the AzureADOrganization class, which provides access to the Azure AD API.
    - user_id: The user ID to get.
    - allow_template_ref: If True, attempt to resolve the user by loading the IAMbic template

    Returns:
    - The `User` instance, representing the user in Azure AD.
    """
    assert user_id or username

    if user_id:
        async with GlobalRetryController(
            fn_identifier="azure_ad.get_user"
        ) as retry_controller:
            fn = functools.partial(azure_ad_organization.get, f"users/{user_id}")
            user = await retry_controller(fn)
            return UserTemplateProperties.from_azure_response(user)

    users = await list_users(
        azure_ad_organization,
        params={"$filter": f"userPrincipalName eq '{username}'"},
    )
    if users:
        return users[0]

    raise Exception(f"User not found with username {username}")


async def create_user(
    azure_ad_organization: AzureADOrganization,
    username: str,
    mail_nickname: Optional[str],
    display_name: str,
) -> Optional[UserTemplateProperties]:
    """
    Create a new user in Azure AD.
    Args:
    - azure_ad_organization (AzureADOrganization): The Azure AD organization to update the user in.
    - username: The name of the user to create.
    - mail_nickname: The mail alias for the user.
    - display_name: The name to display in the address book for the user.

    Returns:
    - An instance of the `UserTemplateProperties` class, representing the created user.
    """

    if ctx.execute:
        log.warning(
            "request data",
            request_data={
                "accountEnabled": True,
                "displayName": display_name,
                "mailNickname": mail_nickname,
                "userPrincipalName": username,
            },
        )

        user = await azure_ad_organization.post(
            "users",
            json={
                "accountEnabled": True,
                "displayName": display_name,
                "mailNickname": mail_nickname,
                "userPrincipalName": username,
                "passwordProfile": {
                    "forceChangePasswordNextSignIn": True,
                    "forceChangePasswordNextSignInWithMfa": azure_ad_organization.require_user_mfa_on_create,
                    "password": secrets.token_urlsafe(15),
                },
            },
        )
        return UserTemplateProperties.from_azure_response(user)


async def update_user_attributes(
    azure_ad_organization: AzureADOrganization,
    template_user: UserTemplateProperties,
    cloud_user: UserTemplateProperties,
    log_params: dict[str, str],
) -> List[ProposedChange]:
    """
    Update the name of a user in Azure AD.
        Args:
        azure_ad_organization (AzureADOrganization): The Azure AD organization to update the user in.
        template_user (UserTemplateProperties): The template representation of the user.
        cloud_user (UserTemplateProperties): The current representation of the user in the cloud.
        log_params (dict): Logging parameters.

    Returns:
        List[ProposedChange]: A list of proposed changes to be applied.
    """
    response: list[ProposedChange] = []
    patch_request = {}

    for attr, value in cloud_user.dict(
        exclude_none=False, exclude={"user_id", "fullname"}
    ).items():
        if (template_value := getattr(template_user, attr)) != value:
            response.append(
                ProposedChange(
                    change_type=ProposedChangeType.UPDATE,
                    resource_id=template_user.user_id,
                    resource_type=template_user.resource_type,
                    attribute=attr,
                    current_value=value,
                    new_value=template_value,
                )
            )

            attr = (
                "username" if attr == "userPrincipalName" else snake_to_camelback(attr)
            )
            patch_request[attr] = template_value

    if ctx.execute and patch_request:
        try:
            await azure_ad_organization.patch(
                f"users/{cloud_user.user_id}",
                json=patch_request,
            )
        except ClientResponseError as err:
            log.exception(
                "Failed to update user in Azure AD",
                **log_params,
            )
            response[0].exceptions_seen = [str(err)]

    return response


async def delete_user(
    azure_ad_organization: AzureADOrganization,
    user: UserTemplateProperties,
    log_params: dict[str, str],
) -> List[ProposedChange]:
    """
    Delete a user in Azure AD.
    Args:
        azure_ad_organization (AzureADOrganization): The Azure AD organization to delete the user from.
        user (UserTemplateProperties): The user to delete.
        log_params (dict): Logging parameters.

    Returns:
        List[ProposedChange]: A list of proposed changes to be applied.
    """
    response: list[ProposedChange] = [
        ProposedChange(
            change_type=ProposedChangeType.DELETE,
            resource_id=user.user_id,
            resource_type=user.resource_type,
            attribute="user",
            change_summary={"user": user.username},
            current_value=user.username,
            new_value=None,
        )
    ]

    if ctx.execute:
        try:
            await azure_ad_organization.delete(f"users/{user.user_id}")
        except ClientResponseError as err:
            log.exception(
                "Failed to delete user in Azure AD",
                **log_params,
            )
            response[0].exceptions_seen = [str(err)]

    return response
