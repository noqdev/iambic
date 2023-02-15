from __future__ import annotations

import asyncio
from itertools import chain
from typing import Any, Optional

from pydantic import Field

from iambic.config.dynamic_config import Config
from iambic.config.models import OktaOrganization
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
from iambic.core.utils import NoqSemaphore
from iambic.okta.models import User, UserStatus
from iambic.okta.user.utils import (
    create_user,
    get_user,
    maybe_deprovision_user,
    update_user_profile,
    update_user_status,
)

OKTA_USER_TEMPLATE_TYPE = "NOQ::Okta::User"
OKTA_GET_USER_SEMAPHORE = NoqSemaphore(get_user, 3)


class Assignment(BaseModel):
    role: str
    resource_set: str


class OktaUserTemplateProperties(BaseModel):
    username: str = Field(..., description="Username of the user")
    idp_name: str = Field(
        ...,
        description="Name of the identity provider that's associated with the user",
    )
    user_id: str = Field("", description="Unique User ID for the user")
    status: UserStatus = Field(UserStatus.active, description="Status of the user")
    profile: dict[str, Any]
    extra: Optional[dict[str, Any]] = Field(
        None, description=("Extra attributes to store for the user")
    )

    @property
    def resource_type(self) -> str:
        return "okta:user"

    @property
    def resource_id(self) -> str:
        return self.user_id


class OktaUserTemplate(BaseTemplate, ExpiryModel):
    template_type: str = "NOQ::Okta::User"
    properties: OktaUserTemplateProperties
    force_delete: bool = Field(
        False,
        description=(
            "If `self.deleted` is true, the user will be force deleted from Okta. "
        ),
    )

    async def apply(
        self, config: Config, context: ExecutionContext
    ) -> TemplateChangeDetails:
        tasks = []
        template_changes = TemplateChangeDetails(
            resource_id=self.properties.user_id,
            resource_type=self.template_type,
            template_path=self.file_path,
        )
        log_params = dict(
            resource_type=self.resource_type,
            resource_name=self.properties.username,
        )

        if self.iambic_managed == IambicManaged.IMPORT_ONLY:
            log_str = "Resource is marked as import only."
            log.info(log_str, **log_params)
            template_changes.proposed_changes = []
            return template_changes

        for okta_organization in config.okta_organizations:
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
        if account_changes and context.execute:
            log.info(
                "Successfully applied resource changes to all Okta organizations.",
                **log_params,
            )
        elif account_changes:
            log.info(
                "Successfully detected required resource changes on all Okta organizations.",
                **log_params,
            )
        else:
            log.debug("No changes detected for resource on any account.", **log_params)

        return template_changes

    @property
    def resource_id(self) -> str:
        return self.properties.user_id

    @property
    def resource_type(self) -> str:
        return "okta:user"

    def apply_resource_dict(
        self, okta_organization: OktaOrganization, context: ExecutionContext
    ):
        return {
            "username": self.properties.username,
            "status": self.properties.status,
            "profile": self.properties.profile,
        }

    async def _apply_to_account(
        self,
        okta_organization: OktaOrganization,
        context: ExecutionContext,
    ) -> AccountChangeDetails:
        await self.remove_expired_resources(context)
        proposed_user = self.apply_resource_dict(okta_organization, context)
        change_details = AccountChangeDetails(
            account=self.properties.idp_name,
            resource_id=self.properties.username,
            new_value=proposed_user,
            proposed_changes=[],
        )

        log_params = dict(
            resource_type=self.properties.resource_type,
            resource_id=self.properties.username,
            organization=str(self.properties.idp_name),
        )

        current_user_task = await OKTA_GET_USER_SEMAPHORE.process(
            [
                {
                    "username": self.properties.username,
                    "user_id": self.properties.user_id,
                    "okta_organization": okta_organization,
                }
            ]
        )
        current_user: Optional[User] = current_user_task[0]
        if current_user:
            change_details.current_value = current_user

        user_exists = bool(current_user)
        tasks = []
        if self.deleted:
            self.properties.status = UserStatus.deprovisioned
            proposed_user["status"] = "deprovisioned"

        if not user_exists and not self.deleted:
            change_details.proposed_changes.append(
                ProposedChange(
                    change_type=ProposedChangeType.CREATE,
                    resource_id=self.properties.username,
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

            current_user: User = await create_user(
                self,
                okta_organization=okta_organization,
                context=context,
            )
            if current_user:
                change_details.current_value = current_user
        if (
            current_user
            and self.deleted
            and current_user.status == UserStatus.deprovisioned
            and proposed_user.get("status") == "deprovisioned"
            and not self.force_delete
        ):
            log.info(
                "User is already deprovisioned. Please delete the user in Okta.",
                **log_params,
            )
            return change_details

        tasks.extend(
            [
                update_user_status(
                    current_user,
                    self.properties.status.value,
                    okta_organization,
                    log_params,
                    context,
                ),
                update_user_profile(
                    self,
                    current_user,
                    self.properties.profile,
                    okta_organization,
                    log_params,
                    context,
                ),
                maybe_deprovision_user(
                    self.deleted, current_user, okta_organization, log_params, context
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
            self.write()
        else:
            log.debug(
                "Successfully finished scanning for drift for resource",
                requires_changes=bool(change_details.proposed_changes),
                **log_params,
            )
        return change_details
