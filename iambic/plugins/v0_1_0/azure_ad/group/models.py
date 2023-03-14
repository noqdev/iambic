from __future__ import annotations

import asyncio
import os
from itertools import chain
from typing import TYPE_CHECKING, Any, List, Optional, Union

from iambic.core.context import ExecutionContext, ctx
from iambic.core.iambic_enum import IambicManaged
from iambic.core.logger import log
from iambic.core.models import (
    AccountChangeDetails,
    BaseModel,
    BaseTemplate,
    ExpiryModel,
    ProposedChange,
    ProposedChangeType,
    TemplateChangeDetails,
)
from iambic.core.utils import normalize_dict_keys
from iambic.plugins.v0_1_0.azure_ad.group.utils import (
    create_group,
    delete_group,
    get_group,
    update_group_attributes,
    update_group_members,
)
from iambic.plugins.v0_1_0.azure_ad.user.models import User, UserSimple
from pydantic import Field

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.azure_ad.iambic_plugin import AzureADConfig
    from iambic.plugins.v0_1_0.azure_ad.models import AzureADOrganization

AZURE_AD_GROUP_TEMPLATE_TYPE = "NOQ::AzureAD::Group"


class GroupTemplateProperties(ExpiryModel, BaseModel):
    name: str = Field(..., description="Name of the group")
    owner: Optional[str] = Field(None, description="Owner of the group")
    idp_name: str = Field(
        ...,
        description="Name of the identity provider that's associated with the group",
    )
    group_id: str = Field(
        "", description="Unique Group ID for the group. Usually it's {idp-name}-{name}"
    )
    description: Optional[str] = Field("", description="Description of the group")
    extra: Any = Field(None, description=("Extra attributes to store"))
    members: List[UserSimple] = Field([], description="Users in the group")

    @property
    def resource_type(self) -> str:
        return "azure_ad:group"

    @property
    def resource_id(self) -> str:
        return self.group_id


class GroupTemplate(BaseTemplate, ExpiryModel):
    template_type = AZURE_AD_GROUP_TEMPLATE_TYPE
    properties: GroupTemplateProperties = Field(
        ..., description="Properties for the Azure AD Group"
    )

    async def apply(
        self, config: AzureADConfig, context: ExecutionContext
    ) -> TemplateChangeDetails:
        tasks = []
        template_changes = TemplateChangeDetails(
            resource_id=self.properties.group_id,
            resource_type=self.template_type,
            template_path=self.file_path,
        )
        log_params = dict(
            resource_type=self.resource_type,
            resource_name=self.properties.name,
        )

        if self.iambic_managed == IambicManaged.IMPORT_ONLY:
            log_str = "Resource is marked as import only."
            log.info(log_str, **log_params)
            template_changes.proposed_changes = []
            return template_changes

        for azure_ad_organization in config.organizations:
            if context.execute:
                log_str = "Applying changes to resource."
            else:
                log_str = "Detecting changes for resource."
            log.info(log_str, idp_name=azure_ad_organization.idp_name, **log_params)
            tasks.append(self._apply_to_account(azure_ad_organization, context))

        account_changes = await asyncio.gather(*tasks)
        template_changes.proposed_changes = [
            account_change
            for account_change in account_changes
            if any(account_change.proposed_changes)
        ]
        if account_changes and context.execute:
            log.info(
                "Successfully applied resource changes to all Azure AD organizations.",
                **log_params,
            )
        elif account_changes:
            log.info(
                "Successfully detected required resource changes on all Azure AD organizations.",
                **log_params,
            )
        else:
            log.debug("No changes detected for resource on any account.", **log_params)

        return template_changes

    @property
    def resource_id(self) -> str:
        return self.properties.group_id

    @property
    def resource_type(self) -> str:
        return "azure_ad:group"

    def apply_resource_dict(
        self, azure_ad_organization: AzureADOrganization, context: ExecutionContext
    ):
        return {
            "name": self.properties.name,
            "description": self.properties.description,
            "members": self.properties.members,
        }

    async def _apply_to_account(
        self, azure_ad_organization: AzureADOrganization, context: ExecutionContext
    ) -> AccountChangeDetails:
        proposed_group = self.apply_resource_dict(azure_ad_organization, context)
        change_details = AccountChangeDetails(
            account=self.properties.idp_name,
            resource_id=self.properties.group_id,
            new_value=proposed_group,
            proposed_changes=[],
        )

        log_params = dict(
            resource_type=self.properties.resource_type,
            resource_id=self.properties.name,
            organization=str(self.properties.idp_name),
        )

        cloud_group: Optional[Group] = await get_group(
            azure_ad_organization, self.properties.group_id, self.properties.name
        )
        if cloud_group:
            change_details.current_value = cloud_group

        group_exists = bool(cloud_group)
        tasks = []

        await self.remove_expired_resources(context)

        if not group_exists and not self.deleted:
            change_details.proposed_changes.append(
                ProposedChange(
                    change_type=ProposedChangeType.CREATE,
                    resource_id=self.properties.group_id,
                    resource_type=self.properties.resource_type,
                )
            )
            log_str = "New resource found in code."
            if not context.execute:
                log.info(log_str, **log_params)
                # Exit now because apply functions won't work if resource doesn't exist
                return change_details

            log_str = f"{log_str} Creating resource..."
            log.info(log_str, **log_params)

            cloud_group: Group = await create_group(
                group_name=self.properties.name,
                idp_name=self.properties.idp_name,
                description=self.properties.description,
                azure_ad_organization=azure_ad_organization,
            )
            if cloud_group:
                change_details.current_value = cloud_group

        if self.deleted:
            change_details.proposed_changes.extend(
                await delete_group(
                    azure_ad_organization,
                    cloud_group,
                    log_params,
                )
            )
        else:
            # TODO: Support group expansion
            tasks.extend(
                [
                    update_group_attributes(
                        azure_ad_organization,
                        self.properties,
                        cloud_group,
                        log_params,
                    ),
                    update_group_members(
                        azure_ad_organization,
                        cloud_group,
                        [
                            member
                            for member in self.properties.members
                            if not member.deleted
                        ],
                        log_params,
                    ),
                ]
            )

            changes_made = await asyncio.gather(*tasks)
            if any(changes_made):
                change_details.proposed_changes.extend(
                    list(chain.from_iterable(changes_made))
                )

        if ctx.execute:
            log.debug(
                "Successfully finished execution for resource",
                changes_made=bool(change_details.proposed_changes),
                **log_params,
            )
            # TODO: Check if deleted, remove git commit the change to ratify it
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

    def set_default_file_path(self, repo_dir: str):
        file_name = f"{self.properties.name}.yaml"
        self.file_path = os.path.expanduser(
            os.path.join(
                repo_dir,
                f"resources/azure_ad/groups/{self.properties.idp_name}/{file_name}",
            )
        )


class GroupAttributes(BaseModel):
    requestable: bool = Field(
        False, description="Whether end-users can request access to group"
    )
    manager_approval_required: bool = Field(
        False, description="Whether a manager needs to approve access to the group"
    )
    approval_chain: List[Union[User, str]] = Field(
        [],
        description="A list of users or groups that need to approve access to the group",
    )
    self_approval_groups: List[str] = Field(
        [],
        description=(
            "If the user is a member of a self-approval group, their request to the group "
            "will be automatically approved"
        ),
    )
    allow_bulk_add_and_remove: bool = Field(
        True,
        description=(
            "Controls whether administrators can automatically approve access to the group"
        ),
    )
    background_check_required: bool = Field(
        False,
        description=("Whether a background check is required to be added to the group"),
    )
    allow_contractors: bool = Field(
        False,
        description=("Whether contractors are allowed to be members of the group"),
    )
    allow_third_party: bool = Field(
        False,
        description=(
            "Whether third-party users are allowed to be a member of the group"
        ),
    )
    emails_to_notify_on_new_members: List[str] = Field(
        [],
        description=(
            "A list of e-mail addresses to notify when new users are added to the group."
        ),
    )


class Group(BaseModel):
    name: str = Field(..., description="Name of the group")
    owner: Optional[str] = Field(None, description="Owner of the group")
    tenant_id: str = Field(
        ...,
        description="ID of the tenant's identity provider that's associated with the group",
    )
    group_id: Optional[str] = Field(
        ...,
        description="Unique Group ID for the group. Usually it's {tenant-id}-{name}",
    )
    description: Optional[str] = Field(None, description="Description of the group")
    members: List[User] = Field([], description="Users in the group")

    @property
    def resource_type(self) -> str:
        return "azure_ad:group"

    @classmethod
    def from_azure_response(cls, azure_response: dict):
        azure_response = normalize_dict_keys(azure_response)
        return cls(
            group_id=azure_response["id"],
            name=azure_response["display_name"],
            tenant_id="?",
            description=azure_response["description"],
            members=[],
        )
