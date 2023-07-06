from __future__ import annotations

import asyncio
import os
from itertools import chain
from typing import TYPE_CHECKING, Any, List, Optional

from pydantic import Field, validator

from iambic.core.context import ctx
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
from iambic.plugins.v0_1_0.okta.group_rule.utils import (
    create_rule,
    get_rule,
    maybe_delete_rule,
    update_rule
)
from iambic.plugins.v0_1_0.okta.models import GroupRule

# TODO Reuse this status or make one of our own?
from okta.models import GroupRuleStatus

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.okta.iambic_plugin import OktaConfig, OktaOrganization

OKTA_GROUP_RULE_TEMPLATE_TYPE = "NOQ::Okta::GroupRule"

class GroupRuleProperties(ExpiryModel, BaseModel):
    name: str = Field(..., description="Name of the group rule")
    rule_id: str = Field(
        "",
        description="Unique ID for the group rule.",
    )
    file_path: str = Field(
        "", description="File path of the group", exclude=True, hidden_from_schema=True
    )
    conditions: str = Field("", description="Rule conditions")
    actions: str = Field([], description="Rule actions")
    # TODO ???
    # extra: Any = Field(None, description=("Extra attributes to store"))
    # identifier: Optional[str] = Field(
    #     None,
    #     description="Identifier for the group. Usually it's the group name",
    #     exclude=True,
    # )

    @classmethod
    def iambic_specific_knowledge(cls) -> set[str]:
        return {"extra", "metadata_commented_dict"}

    @property
    def resource_type(self) -> str:
        return "okta:group_rule"

    @property
    def resource_id(self) -> str:
        return self.rule_id

class OktaGroupRuleTemplate(BaseTemplate, ExpiryModel):
    template_type = OKTA_GROUP_RULE_TEMPLATE_TYPE
    properties: GroupRuleProperties = Field(
        ..., description="Properties for the Okta Group Rule"
    )
    idp_name: str = Field(
        ...,
        description="Name of the identity provider that's associated with the group",
    )

    async def apply(self, config: OktaConfig) -> TemplateChangeDetails:
        tasks = []
        template_changes = TemplateChangeDetails(
            resource_id=self.properties,
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
            if self.idp_name != okta_organization.idp_name:
                continue
            if ctx.execute:
                log_str = "Applying changes to resource."
            else:
                log_str = "Detecting changes for resource."
            log.info(log_str, idp_name=okta_organization.idp_name, **log_params)
            tasks.append(self._apply_to_account(okta_organization))

        account_changes = await asyncio.gather(*tasks)
        template_changes.proposed_changes = [
            account_change
            for account_change in account_changes
            if any(account_change.proposed_changes)
        ]

        proposed_changes = [x for x in account_changes if x.proposed_changes]

        if proposed_changes and ctx.execute:
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
        return self.properties.rule_id

    @property
    def resource_type(self) -> str:
        return "okta:group_rule"

    def set_default_file_path(self, repo_dir: str):
        file_name = f"{self.properties.name}.yaml"
        self.file_path = os.path.expanduser(
            os.path.join(
                repo_dir,
                f"resources/okta/group_rules/{self.idp_name}/{file_name}",
            )
        )

    def apply_resource_dict(self, okta_organization: OktaOrganization):
        return {
            "name": self.properties.name,
            "description": self.properties.description,
            "members": self.properties.members,
        }

    async def _apply_to_account(
        self, okta_organization: OktaOrganization
    ) -> AccountChangeDetails:
        proposed_rule = self.apply_resource_dict(okta_organization)
        change_details = AccountChangeDetails(
            account=self.idp_name,
            resource_id=self.properties.group_rule_id,
            resource_type=self.properties.resource_type,
            new_value=proposed_rule, 
            proposed_changes=[],
        )

        log_params = dict(
            resource_type=self.properties.resource_type,
            resource_id=self.properties.name,
            organization=str(self.idp_name),
        )

        current_rule: Optional[GroupRule] = await get_group_rule(
            self.properties.rule_id, self.properties.name, okta_organization
        )
        if current_rule:
            change_details.current_value = current_rule

            if ctx.command == Command.CONFIG_DISCOVERY:
                # Don't overwrite a resource during config discovery
                change_details.new_value = {}
                return change_details

        rule_exists = bool(current_rule)
        tasks = []

        await self.remove_expired_resources()

        if not rule_exists and not self.deleted:
            change_details.extend_changes(
                [
                    ProposedChange(
                        change_type=ProposedChangeType.CREATE,
                        resource_id=self.properties.rule_id,
                        resource_type=self.properties.resource_type,
                    )
                ]
            )
            log_str = "New resource found in code."
            if not ctx.execute:
                log.info(log_str, **log_params)
                # Exit now because apply functions won't work if resource doesn't exist
                return change_details

            log_str = f"{log_str} Creating resource..."
            log.info(log_str, **log_params)

            current_rule: GroupRule = await create_rule(
                rule_name=self.properties.name,
                idp_name=self.idp_name,
                description=self.properties.description,
                okta_organization=okta_organization,
            )
            if current_rule:
                change_details.current_value = current_rule

        # TODO: Support group expansion
        tasks.extend(
            [
                update_rule_name(
                    current_rule,
                    self.properties.name,
                    okta_organization,
                    log_params,
                ),
                update_rule_description(
                    current_rule,
                    self.properties.description,
                    okta_organization,
                    log_params,
                ),
                # update_rule_logic(
                #     current_group,
                #     [
                #         member
                #         for member in self.properties.members
                #         if not member.deleted
                #     ],
                #     okta_organization,
                #     log_params,
                # ),
                maybe_delete_rule(
                    self.deleted,
                    current_rule,
                    okta_organization,
                    log_params,
                ),
                # TODO
                # upgrade_group_application_assignments
            ]
        )

        changes_made = await asyncio.gather(*tasks)
        if any(changes_made):
            change_details.extend_changes(list(chain.from_iterable(changes_made)))

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
