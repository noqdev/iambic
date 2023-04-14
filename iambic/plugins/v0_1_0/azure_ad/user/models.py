from __future__ import annotations

import asyncio
import typing
from enum import Enum
from itertools import chain
from typing import Optional

from aiohttp import ClientResponseError
from pydantic import Field

from iambic.core.context import ctx
from iambic.core.logger import log
from iambic.core.models import (
    AccountChangeDetails,
    BaseModel,
    ExpiryModel,
    ProposedChange,
    ProposedChangeType,
)
from iambic.core.utils import normalize_dict_keys
from iambic.plugins.v0_1_0.azure_ad.models import AzureADOrganization, AzureADTemplate

if typing.TYPE_CHECKING:
    MappingIntStrAny = typing.Mapping[int | str, any]
    AbstractSetIntStr = typing.AbstractSet[int | str]

AZURE_AD_USER_TEMPLATE_TYPE = "NOQ::AzureAD::User"


class UserStatus(Enum):
    active = "active"
    provisioned = "provisioned"
    deprovisioned = "deprovisioned"


class UserTemplateProperties(BaseModel, ExpiryModel):
    user_id: Optional[str] = Field("", description="Unique identifier for the user")
    username: str
    display_name: str
    mail_nickname: Optional[str]
    given_name: Optional[str]
    employee_id: Optional[str]
    domain: Optional[str]
    fullname: Optional[str]
    status: Optional[UserStatus]

    business_phones: Optional[list[str]] = Field(
        [], description="List of business phone numbers", exclude=True
    )
    id: Optional[str] = Field(
        None, description="Unique identifier for the user", exclude=True
    )
    job_title: Optional[str] = Field(
        None, description="Job title of the user", exclude=True
    )
    mail: Optional[str] = Field(
        None, description="Email address of the user", exclude=True
    )
    mobile_phone: Optional[str] = Field(
        None, description="Mobile phone number of the user", exclude=True
    )
    office_location: Optional[str] = Field(
        None, description="Office location of the user", exclude=True
    )
    preferred_language: Optional[str] = Field(
        None, description="Preferred language of the user", exclude=True
    )
    surname: Optional[str] = Field(
        None, description="Surname of the user", exclude=True
    )
    user_principal_name: Optional[str] = Field(
        None, description="User principal name of the user", exclude=True
    )

    @property
    def resource_type(self) -> str:
        return "azure_ad:user"

    @property
    def resource_id(self) -> str:
        return self.username

    @classmethod
    def from_azure_response(cls, azure_response: dict) -> UserTemplateProperties:
        unwanted_keys = [
            "password_profile",
            "account_enabled",
        ]
        azure_response = normalize_dict_keys(azure_response)
        # Filter unwanted keys
        azure_response = {
            x: y for x, y in azure_response.items() if x not in unwanted_keys
        }
        azure_response = {
            x: y for x, y in azure_response.items() if not x.startswith("@odata")
        }

        return cls(
            user_id=azure_response.get("id"),
            username=azure_response.get("user_principal_name"),
            **azure_response,
        )


class AzureActiveDirectoryUserTemplate(ExpiryModel, AzureADTemplate):
    template_type = AZURE_AD_USER_TEMPLATE_TYPE
    properties: UserTemplateProperties = Field(
        ..., description="Properties for the Azure AD User"
    )

    @property
    def resource_type(self) -> str:
        return "azure_ad:user"

    async def _apply_to_account(
        self, azure_ad_organization: AzureADOrganization
    ) -> AccountChangeDetails:
        from iambic.plugins.v0_1_0.azure_ad.user.utils import (
            create_user,
            delete_user,
            get_user,
            update_user_attributes,
        )

        change_details = AccountChangeDetails(
            account=self.idp_name,
            resource_id=self.resource_id,
            new_value=self.properties.dict(
                exclude={"metadata_commented_dict"}, exclude_none=True
            ),
            proposed_changes=[],
        )
        cloud_user = None

        log_params = dict(
            resource_type=self.resource_type,
            resource_id=self.resource_id,
            organization=str(self.idp_name),
        )

        if self.properties.user_id and not self.deleted:
            try:
                cloud_user: Optional[UserTemplateProperties] = await get_user(
                    azure_ad_organization,
                    self.properties.user_id,
                    self.properties.username,
                )
                change_details.current_value = cloud_user
            except ClientResponseError as err:
                if err.status == 404:
                    err = (
                        f"User not found in Azure AD where id={self.properties.user_id}"
                    )
                    log.exception(
                        "Invalid user_id provided. User not found in Azure AD.",
                        **log_params,
                    )
                change_details.extend_changes(
                    [
                        ProposedChange(
                            change_type=ProposedChangeType.UPDATE,
                            resource_id=self.resource_id,
                            resource_type=self.resource_type,
                            exceptions_seen=[str(err)],
                        )
                    ]
                )
                return change_details

        user_exists = bool(cloud_user)
        tasks = []

        if not user_exists and not self.deleted:
            log_str = "New resource found in code."
            change_details.extend_changes(
                [
                    ProposedChange(
                        change_type=ProposedChangeType.CREATE,
                        resource_id=self.resource_id,
                        resource_type=self.resource_type,
                    )
                ]
            )
            if not ctx.execute:
                log.info(log_str, **log_params)
                # Exit now because apply functions won't work if resource doesn't exist
                return change_details

            log_str = f"{log_str} Creating resource..."
            log.info(log_str, **log_params)

            try:
                cloud_user: UserTemplateProperties = await create_user(
                    azure_ad_organization=azure_ad_organization,
                    username=self.properties.username,
                    display_name=self.properties.display_name,
                    mail_nickname=self.properties.mail_nickname
                    or self.properties.username.split("@")[0],
                )
                self.properties.user_id = cloud_user.user_id
                self.write()
            except ClientResponseError as err:
                log.exception(
                    "Failed to create user in Azure AD",
                    **log_params,
                )
                proposed_change = change_details.proposed_changes.pop(-1)
                proposed_change.exceptions_seen.append(str(err))
                change_details.exceptions_seen.append(proposed_change)
                return change_details

        if self.deleted:
            change_details.extend_changes(
                await delete_user(
                    azure_ad_organization,
                    self.properties,
                    log_params,
                )
            )
        else:
            tasks.append(
                update_user_attributes(
                    azure_ad_organization,
                    self.properties,
                    cloud_user,
                    log_params,
                )
            )

            changes_made = await asyncio.gather(*tasks)
            if any(changes_made):
                change_details.extend_changes(list(chain.from_iterable(changes_made)))

        if ctx.execute and not change_details.exceptions_seen:
            log.debug(
                "Successfully finished execution for resource",
                changes_made=bool(change_details.proposed_changes),
                **log_params,
            )
        elif change_details.exceptions_seen:
            cmd_verb = "apply" if ctx.execute else "scan for"
            log.error(
                f"Failed to successfully {cmd_verb} resource changes",
                **log_params,
            )
        else:
            log.debug(
                "Successfully finished scanning for drift for resource",
                requires_changes=bool(change_details.proposed_changes),
                **log_params,
            )

        return change_details
