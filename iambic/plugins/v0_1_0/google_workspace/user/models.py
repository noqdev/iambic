from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from pydantic import Field

from iambic.core.iambic_enum import IambicManaged
from iambic.core.models import BaseModel, BaseTemplate, ExpiryModel

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
