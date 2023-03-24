from __future__ import annotations

import asyncio
import json
import typing
from enum import Enum
from itertools import chain
from typing import TYPE_CHECKING, Any, List, Optional, Union

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

if TYPE_CHECKING:
    MappingIntStrAny = typing.Mapping[int | str, any]
    AbstractSetIntStr = typing.AbstractSet[int | str]

AZURE_AD_GROUP_TEMPLATE_TYPE = "NOQ::AzureAD::Group"


class MemberDataType(Enum):
    USER = "user"
    GROUP = "group"


class Member(BaseModel, ExpiryModel):
    id: str
    name: str
    data_type: MemberDataType
    """TODO: validate name

    https://learn.microsoft.com/en-us/azure/active-directory/authentication/concept-sspr-policy#userprincipalname-policies-that-apply-to-all-user-accounts

    The total length must not exceed 113 characters
    There can be up to 64 characters before the "@" symbol
    There can be up to 48 characters after the "@" symbol
    """

    @property
    def resource_type(self) -> str:
        return "azure_ad:user"

    @property
    def resource_id(self) -> str:
        return f"{self.name} - {self.id}"

    def dict(
        self,
        *,
        include: Optional[Union[AbstractSetIntStr, MappingIntStrAny]] = None,
        exclude: Optional[Union[AbstractSetIntStr, MappingIntStrAny]] = None,
        by_alias: bool = False,
        skip_defaults: Optional[bool] = None,
        exclude_unset: bool = False,
        exclude_defaults: bool = False,
        exclude_none: bool = False,
    ) -> "DictStrAny":  # noqa
        if not exclude:
            exclude = {"metadata_commented_dict", "deleted"}
        else:
            exclude.add("metadata_commented_dict")
            exclude.add("deleted")

        return json.loads(
            super().json(
                include=include,
                exclude=exclude,
                by_alias=by_alias,
                skip_defaults=skip_defaults,
                exclude_unset=exclude_unset,
                exclude_defaults=exclude_defaults,
                exclude_none=exclude_none,
            )
        )


class GroupTemplateProperties(ExpiryModel, BaseModel):
    name: str = Field(..., description="Name of the group", max_length=256)
    mail_nickname: str = Field(
        ...,
        description="Mail nickname of the group",
        regex=r"^[!#$%&'*+-./0-9=?A-Z^_`a-z{|}~]{1,64}$",
    )
    group_id: Optional[str] = Field(
        None,
        description="Unique Group ID for the group. Usually it's {idp-name}-{name}",
    )
    description: Optional[str] = Field("", description="Description of the group")
    group_types: Optional[list[str]] = Field(
        [], description="Specifies the group type and its membership."
    )
    mail: Optional[str] = Field(description="Email address of the group")
    mail_enabled: Optional[bool] = False
    security_enabled: Optional[bool] = True
    extra: Optional[Any] = Field(None, description="Extra attributes to store")
    is_assignable_to_role: Optional[bool] = Field(
        description="Indicates whether this group can be assigned to an Azure Active Directory role or not."
    )
    membership_rule: Optional[str] = Field(
        description="The rule that determines members for this group if the group is a dynamic group."
    )
    members: Optional[List[Member]] = Field(
        [], description="A list of users in the group"
    )

    @property
    def resource_type(self) -> str:
        return "azure_ad:group"

    @property
    def resource_id(self) -> str:
        return self.mail or self.name

    @classmethod
    def from_azure_response(cls, azure_response: dict):
        azure_response = normalize_dict_keys(azure_response)
        group_id = azure_response.pop("id")
        name = azure_response.pop("display_name")
        return cls(
            group_id=group_id,
            name=name,
            members=[],
            **azure_response,
        )


class GroupTemplate(ExpiryModel, AzureADTemplate):
    template_type = AZURE_AD_GROUP_TEMPLATE_TYPE
    owner: Optional[str] = Field(None, description="Owner of the group")
    properties: GroupTemplateProperties = Field(
        ..., description="Properties for the Azure AD Group"
    )

    @property
    def resource_type(self) -> str:
        return "azure_ad:group"

    def apply_resource_dict(self, azure_ad_organization: AzureADOrganization):
        return {
            "name": self.properties.name,
            "description": self.properties.description,
            "members": self.properties.members,
        }

    async def _apply_to_account(
        self, azure_ad_organization: AzureADOrganization
    ) -> AccountChangeDetails:
        from iambic.plugins.v0_1_0.azure_ad.group.utils import (
            create_group,
            delete_group,
            get_group,
            update_group_attributes,
            update_group_members,
        )

        change_details = AccountChangeDetails(
            account=self.idp_name,
            resource_id=self.resource_id,
            new_value=self.properties.dict(
                exclude={"metadata_commented_dict", "deleted"}, exclude_none=True
            ),
            proposed_changes=[],
        )
        cloud_group = None

        log_params = dict(
            resource_type=self.resource_type,
            resource_id=self.resource_id,
            organization=str(self.idp_name),
        )

        if self.properties.group_id and not self.deleted:
            try:
                cloud_group: Optional[GroupTemplateProperties] = await get_group(
                    azure_ad_organization,
                    self.properties.group_id,
                    self.properties.name,
                )
                change_details.current_value = cloud_group
            except ClientResponseError as err:
                if err.status == 404:
                    err = f"Group not found in Azure AD where id={self.properties.group_id}"
                    log.exception(
                        "Invalid group_id provided. Group not found in Azure AD.",
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

        group_exists = bool(cloud_group)
        tasks = []

        await self.remove_expired_resources()

        if not group_exists and not self.deleted:
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
                cloud_group: GroupTemplateProperties = await create_group(
                    azure_ad_organization=azure_ad_organization,
                    group_name=self.properties.name,
                    description=self.properties.description,
                    mail_enabled=self.properties.mail_enabled,
                    mail_nickname=self.properties.mail_nickname,
                    security_enabled=self.properties.security_enabled,
                    group_types=self.properties.group_types,
                )
                self.properties.group_id = cloud_group.group_id
            except ClientResponseError as err:
                log.exception(
                    "Failed to create user in Azure AD",
                    **log_params,
                )
                proposed_change = change_details.proposed_changes.pop(-1)
                proposed_change.exceptions_seen.append(str(err))
                change_details.extend_changes([proposed_change])
                return change_details

        if self.deleted:
            change_details.extend_changes(
                await delete_group(
                    azure_ad_organization,
                    self.properties,
                    log_params,
                )
            )
        else:
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

            changes_made = await asyncio.gather(*tasks, return_exceptions=True)
            if any(changes_made):
                change_details.extend_changes(list(chain.from_iterable(changes_made)))

        if ctx.execute and not change_details.exceptions_seen:
            log.debug(
                "Successfully finished execution for resource",
                changes_made=bool(change_details.proposed_changes),
                **log_params,
            )
            # TODO: Check if deleted, remove git commit the change to ratify it
            if self.deleted:
                self.delete()
            self.write()
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
