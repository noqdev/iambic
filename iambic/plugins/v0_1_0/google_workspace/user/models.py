from __future__ import annotations

from asyncio import gather
from itertools import chain
from typing import TYPE_CHECKING, Optional

from pydantic import Field

from iambic.core.context import ctx
from iambic.core.iambic_enum import Command, IambicManaged
from iambic.core.logger import log
from iambic.core.models import (
    AccountChangeDetails,
    BaseModel,
    BaseTemplate,
    ExpiryModel,
)
from iambic.plugins.v0_1_0.google_workspace.user.utils import (
    get_user,
    maybe_delete_user,
    update_user_email,
    update_user_name,
)

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.google_workspace.iambic_plugin import GoogleProject


GOOGLE_USER_TEMPLATE_TYPE = "NOQ::GoogleWorkspace::User"


# https://developers.google.com/admin-sdk/directory/reference/rest/v1/users#UserName
class WorkspaceUserName(BaseModel):
    family_name: str = Field(
        alias="familyName",
        description="The user's last name. Required when creating a user account.",
    )

    given_name: str = Field(
        alias="givenName",
        description="The user's first name. Required when creating a user account.",
    )

    display_name: Optional[str] = Field(
        alias="displayName",
        description="The user's display name. Limit: 256 characters.",
    )


# https://developers.google.com/admin-sdk/directory/reference/rest/v1/users
class WorkspaceUser(BaseModel, ExpiryModel):
    primary_email: str = Field(
        description="The user's primary email address. This property is required in a request to create a user account. The primaryEmail must be unique and cannot be an alias of another user.",
    )
    id: Optional[str] = Field(
        None,
        description="The unique ID for the user. A user id can be used as a user request URI's userKey.",
    )
    name: WorkspaceUserName = Field(
        description="Holds the given and family names of the user, and the read-only fullName value. The maximum number of characters in the givenName and in the familyName values is 60. In addition, name values support unicode/UTF-8 characters, and can contain spaces, letters (a-z), numbers (0-9), dashes (-), forward slashes (/), and periods (.). For more information about character usage rules, see the administration help center. Maximum allowed data size for this field is 1KB.",
    )

    domain: str = Field(
        description="this is not direct from user object from google response, but since user maps to a domain, we need to keep track of this information",
    )

    @property
    def resource_type(self):
        return "google:user"

    @property
    def resource_id(self):
        return self.primary_email


class GoogleWorkspaceUserTemplate(BaseTemplate, ExpiryModel):
    template_type = GOOGLE_USER_TEMPLATE_TYPE
    template_schema_url = (
        "https://docs.iambic.org/reference/schemas/google_workspace_user_template"
    )
    # owner metadata seems strange for a user (maybe it makes more sense if its machine user)
    # owner: Optional[str] = Field(None, description="Owner of the group")
    properties: WorkspaceUser

    async def _apply_to_account(
        self, google_project: GoogleProject
    ) -> AccountChangeDetails:
        proposed_user = {
            # Populate user properties here, similar to apply_resource_dict
            "primaryEmail": self.properties.primary_email,
            "name": self.properties.name,
            # ... other properties
        }

        change_details = AccountChangeDetails(
            account=self.properties.domain,
            resource_id=self.properties.primary_email,
            resource_type=self.resource_type,
            new_value=proposed_user,
            proposed_changes=[],
        )

        log_params = {
            "resource_type": self.resource_type,
            "resource_id": self.properties.primary_email,
            "account": str(self.properties.domain),
        }

        current_user = await get_user(
            self.properties.primary_email, self.properties.domain, google_project
        )

        if current_user:
            change_details.current_value = current_user
            if ctx.command == Command.CONFIG_DISCOVERY:
                change_details.new_value = {}
                return change_details

        user_exists = bool(current_user)

        tasks = []

        await self.remove_expired_resources()

        if not user_exists:
            if self.deleted:
                log.info(
                    "Resource is marked for deletion but does not exist in the cloud. Skipping."
                )
                return change_details
            # Handle user creation here
            await create_user(
                primary_email=self.properties.primary_email,
                name=self.properties.name,
                domain=self.properties.domain,
                google_project=google_project,
            )

        tasks.extend(
            [
                update_user_email(
                    current_user.properties.email,
                    self.properties.primary_email,
                    log_params,
                ),
                update_user_name(
                    current_user.properties.name, self.properties.name, log_params
                ),
                # Add more update functions for other user properties
                maybe_delete_user(self, google_project, log_params),
            ]
        )

        changes_made = await gather(*tasks)
        if any(changes_made):
            change_details.extend_changes(list(chain.from_iterable(changes_made)))

        if ctx.execute:
            log.debug(
                "Successfully finished execution for resource",
                changes_made=bool(change_details.proposed_changes),
                **log_params,
            )
            if self.deleted:
                self.delete()
            self.write()
        else:
            log.debug(
                "Successfully finished scanning for drift for resource",
                requires_changes=bool(change_details.proposed_changes),
                **log_params,
            )
        return change_details

    @property
    def resource_type(self):
        return "google:user"

    @property
    def resource_id(self) -> str:
        return self.properties.primary_email

    @property
    def default_file_path(self):
        file_name = f"{self.properties.primary_email.split('@')[0]}.yaml"
        return f"resources/google/users/{self.properties.domain}/{file_name}"

    def _is_iambic_import_only(self, google_project: GoogleProject):
        return (
            google_project.iambic_managed == IambicManaged.IMPORT_ONLY
            or self.iambic_managed == IambicManaged.IMPORT_ONLY
        )


# https://googleapis.github.io/google-api-python-client/docs/dyn/admin_directory_v1.users.html#list
async def get_user_template(
    service, user: dict, domain: str
) -> GoogleWorkspaceUserTemplate:
    # comment out because we don't have to make yet another network call
    # members = await get_group_members(service, group)

    file_name = f"{user['primaryEmail'].split('@')[0]}.yaml"
    return GoogleWorkspaceUserTemplate(
        file_path=f"resources/google/users/{domain}/{file_name}",
        properties=dict(
            domain=domain,
            name=user["name"],
            primary_email=user["primaryEmail"],
        ),
    )
