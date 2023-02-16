from __future__ import annotations

import asyncio
from enum import Enum
from typing import TYPE_CHECKING

from iambic.core.context import ExecutionContext
from iambic.core.logger import log
from iambic.core.models import (
    AccountChangeDetails,
    BaseTemplate,
    ExpiryModel,
    TemplateChangeDetails,
)

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.google.iambic_plugin import GoogleConfig, GoogleProject


class WhoCanInvite(Enum):
    ALL_MANAGERS_CAN_INVITE = "ALL_MANAGERS_CAN_INVITE"
    ALL_MEMBERS_CAN_INVITE = "ALL_MEMBERS_CAN_INVITE"


class WhoCanJoin(Enum):
    ALL_IN_DOMAIN_CAN_JOIN = "ALL_IN_DOMAIN_CAN_JOIN"
    ANYONE_CAN_JOIN = "ANYONE_CAN_JOIN"
    CAN_REQUEST_TO_JOIN = "CAN_REQUEST_TO_JOIN"


class WhoCanPostMessage(Enum):
    ALL_IN_DOMAIN_CAN_POST = "ALL_IN_DOMAIN_CAN_POST"
    ALL_MANAGERS_CAN_POST = "ALL_MANAGERS_CAN_POST"
    ALL_MEMBERS_CAN_POST = "ALL_MEMBERS_CAN_POST"
    ANYONE_CAN_POST = "ANYONE_CAN_POST"
    NONE_CAN_POST = "NONE_CAN_POST"


class WhoCanViewGroup(Enum):
    ALL_IN_DOMAIN_CAN_VIEW = "ALL_IN_DOMAIN_CAN_VIEW"
    ALL_MANAGERS_CAN_VIEW = "ALL_MANAGERS_CAN_VIEW"
    ALL_MEMBERS_CAN_VIEW = "ALL_MEMBERS_CAN_VIEW"
    ANYONE_CAN_VIEW = "ANYONE_CAN_VIEW"


class WhoCanViewMembership(Enum):
    ALL_IN_DOMAIN_CAN_VIEW = "ALL_IN_DOMAIN_CAN_VIEW"
    ALL_MANAGERS_CAN_VIEW = "ALL_MANAGERS_CAN_VIEW"
    ALL_MEMBERS_CAN_VIEW = "ALL_MEMBERS_CAN_VIEW"
    ANYONE_CAN_VIEW = "ANYONE_CAN_VIEW"


class GroupMemberRole(Enum):
    OWNER = "OWNER"
    MANAGER = "MANAGER"
    MEMBER = "MEMBER"


class GroupMemberSubscription(Enum):
    EACH_EMAIL = "EACH_EMAIL"
    DIGEST = "DIGEST"
    ABRIDGED = "ABRIDGED"
    NO_EMAIL = "NO_EMAIL"


class Posting(Enum):
    ALLOWED = "ALLOWED"
    NOT_ALLOWED = "NOT_ALLOWED"
    MODERATED = "MODERATED"


class GroupMemberType(Enum):
    USER = "USER"
    GROUP = "GROUP"
    EXTERNAL = "EXTERNAL"


class GroupMemberStatus(Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    PENDING = "PENDING"
    UNDEFINED = "UNDEFINED"


class GoogleTemplate(BaseTemplate, ExpiryModel):
    async def _apply_to_account(
        self,
        google_project: GoogleProject,
        context: ExecutionContext,
    ) -> AccountChangeDetails:
        raise NotImplementedError

    async def apply(
        self, config: GoogleConfig, context: ExecutionContext
    ) -> TemplateChangeDetails:
        tasks = []
        template_changes = TemplateChangeDetails(
            resource_id=self.properties.email,
            resource_type=self.template_type,
            template_path=self.file_path,
        )
        log_params = dict(
            resource_type=self.resource_type, resource_id=self.resource_id
        )
        for account in config.projects:
            # if evaluate_on_google_account(self, account):
            if context.execute:
                log_str = "Applying changes to resource."
            else:
                log_str = "Detecting changes for resource."
            log.info(log_str, **log_params)
            tasks.append(self._apply_to_account(account, context))

        account_changes = await asyncio.gather(*tasks)
        template_changes.proposed_changes = [
            account_change
            for account_change in account_changes
            if any(account_change.proposed_changes)
        ]
        if account_changes and context.execute:
            log.info(
                "Successfully applied resource changes to all Google projects.",
                **log_params,
            )
        elif account_changes:
            log.info(
                "Successfully detected required resource changes on all Google projects.",
                **log_params,
            )
        else:
            log.debug("No changes detected for resource on any account.", **log_params)

        return template_changes

    @property
    def resource_id(self) -> str:
        return self.properties.email

    @property
    def resource_type(self) -> str:
        return "google:group"
