from __future__ import annotations

import functools
from typing import TYPE_CHECKING, List

from iambic.core.utils import GlobalRetryController
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
    user_id: str = None,
    username: str = None,
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
