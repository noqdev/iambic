from __future__ import annotations

import asyncio
from itertools import chain
from typing import TYPE_CHECKING, Any, List, Optional

from pydantic import Field

from iambic.core.context import ExecutionContext
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
from iambic.plugins.v0_1_0.azure_ad.group.utils import (
    create_group,
    get_group,
    maybe_delete_group,
    update_group_description,
    update_group_members,
    update_group_name,
)
from iambic.plugins.v0_1_0.azure_ad.models import UserStatus

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.azure_ad.iambic_plugin import (
        AzureADConfig,
        AzureADOrganization,
    )

AZURE_AD_GROUP_TEMPLATE_TYPE = "NOQ::AzureAD::Group"


class UserSimple(BaseModel, ExpiryModel):
    username: str
    status: Optional[UserStatus] = UserStatus.active

    @property
    def resource_type(self) -> str:
        return "azure_ad:user"

    @property
    def resource_id(self) -> str:
        return self.username


class User(UserSimple):
    idp_name: str
    user_id: Optional[str]
    domain: Optional[str]
    fullname: Optional[str]
    created: Optional[str]
    updated: Optional[str]
    groups: Optional[List[str]]
    background_check_status: Optional[bool]
    extra: Any = Field(None, description=("Extra attributes to store"))


class AzureADGroupTemplateProperties(ExpiryModel, BaseModel):
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


class AzureADGroupTemplate(BaseTemplate, ExpiryModel):
    template_type = AZURE_AD_GROUP_TEMPLATE_TYPE
    properties: AzureADGroupTemplateProperties = Field(
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

        current_group: Optional[AzureADGroup] = await get_group(
            self.properties.group_id, self.properties.name, azure_ad_organization
        )
        if current_group:
            change_details.current_value = current_group

        group_exists = bool(current_group)
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

            current_group: AzureADGroup = await create_group(
                group_name=self.properties.name,
                idp_name=self.properties.idp_name,
                description=self.properties.description,
                azure_ad_organization=azure_ad_organization,
                context=context,
            )
            if current_group:
                change_details.current_value = current_group

        # TODO: Support group expansion
        tasks.extend(
            [
                update_group_name(
                    current_group,
                    self.properties.name,
                    azure_ad_organization,
                    log_params,
                    context,
                ),
                update_group_description(
                    current_group,
                    self.properties.description,
                    azure_ad_organization,
                    log_params,
                    context,
                ),
                update_group_members(
                    current_group,
                    [
                        member
                        for member in self.properties.members
                        if not member.deleted
                    ],
                    azure_ad_organization,
                    log_params,
                    context,
                ),
                maybe_delete_group(
                    self.deleted,
                    current_group,
                    azure_ad_organization,
                    log_params,
                    context,
                ),
            ]
        )

        changes_made = await asyncio.gather(*tasks)
        if any(changes_made):
            change_details.proposed_changes.extend(
                list(chain.from_iterable(changes_made))
            )

        if context.execute:
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
