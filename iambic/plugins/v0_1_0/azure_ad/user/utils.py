from __future__ import annotations

import functools
from typing import TYPE_CHECKING, List

from iambic.core.utils import GlobalRetryController
from iambic.plugins.v0_1_0.azure_ad.user.models import User

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.azure_ad.models import AzureADOrganization


async def list_all_users(azure_ad_organization: AzureADOrganization) -> List[User]:
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
        fn = functools.partial(azure_ad_organization.list, "users")
        users = await retry_controller(fn)

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
