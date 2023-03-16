from __future__ import annotations

import asyncio
import os
from itertools import chain
from typing import TYPE_CHECKING, Any, List, Optional

from pydantic import Field, validator

from iambic.core.context import ExecutionContext, ctx
from iambic.core.iambic_enum import Command, IambicManaged
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
from iambic.plugins.v0_1_0.okta.group.utils import (
    create_group,
    get_group,
    maybe_delete_group,
    update_group_description,
    update_group_members,
    update_group_name,
)
from iambic.plugins.v0_1_0.okta.models import Group, UserStatus

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.okta.iambic_plugin import OktaConfig, OktaOrganization

OKTA_GROUP_TEMPLATE_TYPE = "NOQ::Okta::Group"


class UserSimple(BaseModel, ExpiryModel):
    username: str
    status: Optional[UserStatus] = UserStatus.active

    @property
    def resource_type(self) -> str:
        return "okta:user"

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


class OktaGroupTemplateProperties(ExpiryModel, BaseModel):
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

    @classmethod
    def iambic_specific_knowledge(cls) -> set[str]:
        return {"extra", "metadata_commented_dict"}

    @property
    def resource_type(self) -> str:
        return "okta:group"

    @property
    def resource_id(self) -> str:
        return self.group_id

    @validator("members")
    def sort_groups(cls, v: list[UserSimple]):
        sorted_v = sorted(v, key=lambda member: member.username)
        return sorted_v


class OktaGroupTemplate(BaseTemplate, ExpiryModel):
    template_type = OKTA_GROUP_TEMPLATE_TYPE
    properties: OktaGroupTemplateProperties = Field(
        ..., description="Properties for the Okta Group"
    )

    async def apply(
        self, config: OktaConfig, context: ExecutionContext
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

        for okta_organization in config.organizations:
            # if evaluate_on_google_account(self, account):
            if context.execute:
                log_str = "Applying changes to resource."
            else:
                log_str = "Detecting changes for resource."
            log.info(log_str, idp_name=okta_organization.idp_name, **log_params)
            tasks.append(self._apply_to_account(okta_organization, context))

        account_changes = await asyncio.gather(*tasks)
        template_changes.proposed_changes = [
            account_change
            for account_change in account_changes
            if any(account_change.proposed_changes)
        ]

        proposed_changes = [x for x in account_changes if x.proposed_changes]

        if proposed_changes and context.execute:
            log.info(
                "Successfully applied all or some resource changes to all Okta organizations. Any unapplied resources will have an accompanying error message.",
                **log_params,
            )
        elif proposed_changes:
            log.info(
                "Successfully detected all or some required resource changes on all Okta organizations. Any unapplied resources will have an accompanying error message.",
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
        return "okta:group"

    def set_default_file_path(self, repo_dir: str):
        file_name = f"{self.properties.name}.yaml"
        self.file_path = os.path.expanduser(
            os.path.join(
                repo_dir,
                f"resources/okta/groups/{self.properties.idp_name}/{file_name}",
            )
        )

    def apply_resource_dict(
        self, okta_organization: OktaOrganization, context: ExecutionContext
    ):
        return {
            "name": self.properties.name,
            "description": self.properties.description,
            "members": self.properties.members,
        }

    async def _apply_to_account(
        self, okta_organization: OktaOrganization, context: ExecutionContext
    ) -> AccountChangeDetails:
        proposed_group = self.apply_resource_dict(okta_organization, context)
        change_details = AccountChangeDetails(
            account=self.properties.idp_name,
            resource_id=self.properties.group_id,
            new_value=proposed_group,  # TODO fix
            proposed_changes=[],
        )

        log_params = dict(
            resource_type=self.properties.resource_type,
            resource_id=self.properties.name,
            organization=str(self.properties.idp_name),
        )

        current_group: Optional[Group] = await get_group(
            self.properties.group_id, self.properties.name, okta_organization
        )
        if current_group:
            change_details.current_value = current_group

            if ctx.command == Command.CONFIG_DISCOVERY:
                # Don't overwrite a resource during config discovery
                change_details.new_value = {}
                return change_details

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

            current_group: Group = await create_group(
                group_name=self.properties.name,
                idp_name=self.properties.idp_name,
                description=self.properties.description,
                okta_organization=okta_organization,
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
                    okta_organization,
                    log_params,
                    context,
                ),
                update_group_description(
                    current_group,
                    self.properties.description,
                    okta_organization,
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
                    okta_organization,
                    log_params,
                    context,
                ),
                maybe_delete_group(
                    self.deleted,
                    current_group,
                    okta_organization,
                    log_params,
                    context,
                ),
                # TODO
                # upgrade_group_application_assignments
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
