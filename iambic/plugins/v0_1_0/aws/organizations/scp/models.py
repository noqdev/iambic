from __future__ import annotations

import asyncio
import json
from enum import Enum
from itertools import chain
from typing import TYPE_CHECKING, Callable, List, Optional, TypedDict, Union

from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field, validator

from iambic.core.context import ctx
from iambic.core.iambic_enum import Command
from iambic.core.logger import log
from iambic.core.models import (
    AccountChangeDetails,
    BaseModel,
    ExpiryModel,
    ProposedChange,
    ProposedChangeType,
)
from iambic.core.utils import normalize_dict_keys, plugin_apply_wrapper
from iambic.plugins.v0_1_0.aws.iam.models import Path
from iambic.plugins.v0_1_0.aws.iam.policy.models import PolicyStatement
from iambic.plugins.v0_1_0.aws.models import (
    AccessModel,
    AWSAccount,
    AWSTemplate,
    Description,
    StatementEffect,
    Tag,
)
from iambic.plugins.v0_1_0.aws.organizations.scp.utils import (
    apply_update_policy,
    apply_update_policy_tags,
    apply_update_policy_targets,
    create_policy,
    delete_policy,
    get_policy,
    service_control_policy_is_enabled,
)

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig
    from iambic.plugins.v0_1_0.aws.models import AWSOrganization


AWS_SCP_POLICY_TEMPLATE = "NOQ::AWS::Organizations::SCP"


class ServiceControlPolicyTargetItemType(str, Enum):
    ACCOUNT = "ACCOUNT"
    ORGANIZATIONAL_UNIT = "ORGANIZATIONAL_UNIT"
    ROOT = "ROOT"


class OrganizationsPolicyType(str, Enum):
    """
    AWS Organizations supports the following policy types. You specify the policy type when you create a policy.

    Possible values:
        - TAG_POLICY
        - BACKUP_POLICY
        - AISERVICES_OPT_OUT_POLICY

    Ref:
        - https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/organizations/client/list_policies.html
    """

    SERVICE_CONTROL_POLICY = "SERVICE_CONTROL_POLICY"
    TAG_POLICY = "TAG_POLICY"
    BACKUP_POLICY = "BACKUP_POLICY"
    AISERVICES_OPT_OUT_POLICY = "AISERVICES_OPT_OUT_POLICY"


class OutputModels(PydanticBaseModel):
    """Response models from AWS Organizations client"""

    class Config:
        use_enum_values = True


class PolicyTargetProperties(BaseModel):
    """
    Note:
    - Root - A string that begins with “r-” followed by from 4 to 32 lowercase letters or digits.
    - Account - A string that consists of exactly 12 digits.
    - Organizational unit (OU) - A string that begins with “ou-” followed by from 4 to 32 lowercase letters or digits (the ID of the root
    that the OU is in). This string is followed by a second “-” dash and from 8 to 32 additional lowercase letters or digits.
    """

    organizational_units: list[str] = Field(default=[], description="List of OUs ids")
    accounts: list[str] = Field(
        default=[], description="List of accounts (names or ids)"
    )
    roots: list[str] = Field(default=[], description="List of root ids")

    @property
    def resource_type(self):
        return "aws:iam:scp_policy:target"

    @property
    def resource_id(self):
        return "|".join(self.organizational_units + self.accounts + self.roots)

    @staticmethod
    def parse_targets(targets: list, config: AWSConfig):
        data = dict(organizational_units=[], accounts=[], roots=[])

        for target in targets:
            key = "accounts"
            target_id = target.get("target_id")
            if target_id.startswith("o-") or target_id.startswith("ou-"):
                key = "organizational_units"
            elif target_id.startswith("r-"):
                key = "roots"
            else:
                target_id = list(
                    map(
                        lambda a: a.account_name,
                        filter(lambda a: a.account_id == target_id, config.accounts),
                    )
                )[0]

            data[key].append(target_id)

        return data

    @staticmethod
    def unparse_targets(targets: list[str], config: AWSConfig):
        data = []

        for target in targets:
            if (
                target.startswith("o-")
                or target.startswith("ou-")
                or target.startswith("r-")
            ):
                target_id = target
            elif target.isdigit() and len(target) == 12:
                # warn: it could be possible that a person has an account name with 12 digits
                target_id = target
            else:
                target_id = list(
                    map(
                        lambda a: a.account_id,
                        filter(lambda a: a.account_name == target, config.accounts),
                    )
                )[0]

            data.append(target_id)

        return data


class PolicyDocument(AccessModel, ExpiryModel):
    version: str = "2012-10-17"
    statement: Union[List[PolicyStatement], PolicyStatement] = Field(
        ...,
        description="List of policy statements",
    )

    @property
    def resource_type(self):
        return "aws:policy_document"

    @property
    def resource_id(self):
        return self.statement.sid

    @staticmethod
    def parse_raw_policy(resource_raw) -> "PolicyDocument":
        resource = json.loads(resource_raw)
        resource = normalize_dict_keys(resource)
        return PolicyDocument(**resource)  # type: ignore

    @validator("statement")
    def validate_statement(cls, statements):
        keys = ["principal", "not_principal", "not_resource"]
        for key in keys:
            for statement in statements:
                if getattr(statement, key, None):
                    raise ValueError(f"{key} is not supported")
        return statements


class PolicyProperties(BaseModel):
    policy_id: Optional[str] = Field(
        None,
        description="The ID of the policy, it is optional when creating a new policy",
        required=False,
    )
    policy_name: str
    path: Optional[Union[str, List["Path"]]] = "/"
    description: Optional[Union[str, list[Description]]] = Field(
        "",
        description="Description of the role",
    )
    type: OrganizationsPolicyType = Field(
        default=OrganizationsPolicyType.SERVICE_CONTROL_POLICY
    )
    aws_managed: bool = Field(False)
    policy_document: Union[PolicyDocument, List[PolicyDocument]] = Field(
        ...,
        description="Policy document, Unsupported elements: Principal, NotPrincipal, NotResource",
    )
    targets: PolicyTargetProperties = Field(default=None)

    tags: Optional[List[Tag]] = Field(
        [],
        description="List of tags attached to the role",
    )

    @property
    def resource_type(self):
        return "aws:iam:scp_policy:properties"

    @property
    def resource_id(self):
        return self.policy_name

    @validator("policy_document")
    def sort_policy_document(cls, v: list[PolicyDocument]):
        if not isinstance(v, list):
            return v
        sorted_v = sorted(v, key=lambda d: d.access_model_sort_weight())
        return sorted_v

    @classmethod
    def sort_func(cls, attribute_name: str) -> Callable:
        def _sort_func(obj):
            return f"{getattr(obj, attribute_name)}!{obj.access_model_sort_weight()}"

        return _sort_func

    @validator("tags")
    def sort_tags(cls, v: list[Tag]) -> list[Tag]:
        sorted_v = sorted(v, key=cls.sort_func("key"))
        return sorted_v


class AwsScpPolicyTemplate(AWSTemplate, AccessModel):
    template_type = AWS_SCP_POLICY_TEMPLATE
    template_schema_url = (
        "https://docs.iambic.org/reference/schemas/aws_scp_policy_template"
    )
    organization_account_needed: bool = Field(
        True,
        description="This template needs an organization account to be applied",
    )
    ARN_TEMPLATE = "arn:aws:organizations::{account_id}:policy/{organization_unit}/service_control_policy/{policy_id}"

    properties: PolicyProperties = Field(
        description="The properties of the scp policy",
    )
    account_id: str
    org_id: str

    def get_arn(self) -> str:
        return self.ARN_TEMPLATE.format(
            account_id=self.account_id if not self.properties.aws_managed else "aws",
            organization_unit=self.org_id,
            policy_id=self.properties.policy_id,
        )

    def _apply_resource_dict(self, aws_account: AWSAccount = None) -> dict:
        resource_dict = super()._apply_resource_dict(aws_account)
        resource_dict["Arn"] = self.get_arn()
        return resource_dict

    async def _apply_to_account(self, aws_account: AWSAccount) -> AccountChangeDetails:
        if self.account_id != aws_account.account_id:
            return AccountChangeDetails(
                account=str(aws_account),
                resource_id=self.properties.resource_id,
                resource_type=self.resource_type,
                new_value={},
                current_value={},
                proposed_changes=[],
                exceptions_seen=[],
            )  # type: ignore

        client = await aws_account.get_boto3_client("organizations")

        if not (await service_control_policy_is_enabled(client)):
            log.info("Service control policy is not enabled in the organization")
            return AccountChangeDetails(
                account=str(aws_account),
                resource_id=self.properties.resource_id,
                resource_type=self.resource_type,
                new_value={},
                current_value={},
                proposed_changes=[],
                exceptions_seen=[],
            )  # type: ignore

        account_policy = self.apply_resource_dict(aws_account)
        policy_name = account_policy.get("PolicyName", "")

        account_change_details = AccountChangeDetails(
            account=str(aws_account),
            resource_id=self.properties.resource_id,
            resource_type=self.resource_type,
            new_value=dict(**account_policy),
            proposed_changes=[],
            exceptions_seen=[],
        )  # type: ignore

        log_params = dict(
            resource_type=self.resource_type,
            resource_id=self.properties.resource_id,
            account=str(aws_account),
        )

        current_policy = None
        if account_policy.get("PolicyId"):
            current_policy = await get_policy(client, account_policy.get("PolicyId"))
            current_policy = current_policy.dict()

        if current_policy:
            # UPDATE POLICY
            account_change_details.current_value = {**current_policy}

            if ctx.command == Command.CONFIG_DISCOVERY:
                # Don't overwrite a resource during config discovery
                account_change_details.new_value = {}
                return account_change_details

        if self.is_delete_action(aws_account):
            # DELETE POLICY
            if current_policy:
                account_change_details.new_value = None
                proposed_changes = [
                    ProposedChange(
                        change_type=ProposedChangeType.DELETE,
                        resource_id=self.properties.resource_id,
                        resource_type=self.resource_type,
                    )  # type: ignore
                ]
                log_str = "Active resource found with deleted=false."
                if ctx.execute:
                    log_str = f"{log_str} Deleting resource..."
                log.debug(log_str, **log_params)

                if ctx.execute:
                    apply_awaitable = delete_policy(
                        client, account_policy.get("PolicyId"), log_params
                    )
                    proposed_changes = await plugin_apply_wrapper(
                        apply_awaitable, proposed_changes
                    )

                account_change_details.extend_changes(proposed_changes)

            return account_change_details

        if current_policy:
            args = [
                client,
                account_policy,
                current_policy,
                log_params,
                aws_account,
            ]

            tasks = [
                method(*args)
                for method in (
                    apply_update_policy,
                    apply_update_policy_targets,
                    apply_update_policy_tags,
                )
            ]

            changes_made: list[list[ProposedChange]] = await asyncio.gather(*tasks)
            if any(changes_made):
                account_change_details.extend_changes(
                    list(chain.from_iterable(changes_made))
                )
                if current_policy.get("Name") != account_policy.get("PolicyName"):
                    self.identifier = account_policy["PolicyName"]
                    self.write()
        else:
            proposed_changes = [
                ProposedChange(
                    change_type=ProposedChangeType.CREATE,
                    resource_id=policy_name,
                    resource_type=self.resource_type,
                    change_summary=account_policy,
                )  # type: ignore
            ]
            log_str = "New resource found in code."
            if not ctx.execute:
                # Exit now because apply functions won't work if resource doesn't exist
                log.debug(log_str, **log_params)
                account_change_details.extend_changes(proposed_changes)
                return account_change_details

            log.debug(f"{log_str} Creating resource...", **log_params)

            apply_awaitable = create_policy(client, account_policy)
            account_change_details.extend_changes(
                await plugin_apply_wrapper(apply_awaitable, proposed_changes)
            )

            self.properties.policy_id = account_policy.get("PolicyId")
            current_policy = await get_policy(client, account_policy.get("PolicyId"))
            current_policy = current_policy.dict()

            args = [client, account_policy, current_policy, log_params, aws_account]

            tasks = [
                apply_update_policy_tags(*args),
                apply_update_policy_targets(*args),
            ]

            changes_made: list[list[ProposedChange]] = await asyncio.gather(*tasks)
            if any(changes_made):
                account_change_details.extend_changes(
                    list(chain.from_iterable(changes_made))
                )

            # name and identifier must match
            self.identifier = current_policy.get("Name", self.identifier)
            self.write()

        self.__log_after_apply(account_change_details, log_params)

        return account_change_details

    def is_delete_action(self, aws_account):
        deleted = self.get_attribute_val_for_account(aws_account, "deleted", False)
        if isinstance(deleted, list):
            deleted = deleted[0].deleted

        return deleted

    def __log_after_apply(self, account_change_details, log_params):
        if ctx.execute and not account_change_details.exceptions_seen:
            log.debug(
                "Successfully finished execution on account for resource",
                changes_made=bool(account_change_details.proposed_changes),
                **log_params,
            )
        elif account_change_details.exceptions_seen:
            log.error(
                "Unable to finish execution on account for resource",
                exceptions_seen=[
                    cd.exceptions_seen for cd in account_change_details.exceptions_seen
                ],
                **log_params,
            )
        else:
            log.debug(
                "Successfully finished scanning for drift on account for resource",
                requires_changes=bool(account_change_details.proposed_changes),
                **log_params,
            )

    @staticmethod
    def factory_template_props(
        account_id: str,
        policy: ServiceControlPolicyItem,
        config: AWSConfig,
        organization: AWSOrganization,
    ):
        template_params = dict(
            identifier=policy.Name,
            account_id=account_id,
            org_id=organization.org_id,
        )

        template_properties = dict(
            policy_id=policy.Id,
            policy_name=policy.Name,
            description=policy.Description,
            type=policy.Type,
            aws_managed=policy.AwsManaged,
            policy_document=dict(
                version=policy.PolicyDocument.Version,
                statement=policy.PolicyDocument.Statement,
            ),
        )

        if policy.Targets:
            template_properties.update(
                targets=PolicyTargetProperties.parse_obj(
                    PolicyTargetProperties.parse_targets(
                        [normalize_dict_keys(t.dict()) for t in policy.Targets],
                        config,
                    )
                )  # type: ignore
            )

        if policy.Tags:
            template_properties.update(
                tags=[normalize_dict_keys(t.dict()) for t in policy.Tags]  # type: ignore
            )
        return template_params, template_properties


class PolicyStatementItem(OutputModels):
    Sid: Optional[str]
    Effect: StatementEffect
    Action: Optional[Union[list[str], str]]
    NotAction: Optional[Union[list[str], str]]
    Resource: Union[list[str], str]
    Condition: Optional[dict]


class PolicyDocumentItem(OutputModels):
    Version: str
    Statement: Union[list[PolicyStatementItem], PolicyStatementItem]


class ServiceControlPolicyTargetItem(OutputModels):
    TargetId: str = Field(
        description="""
Root - A string that begins with “r-” followed by from 4 to 32 lowercase
letters or digits.
Account - A string that consists of exactly 12 digits.
Organizational unit (OU) - A string that begins with “ou-” followed by
from 4 to 32 lowercase letters or digits (the ID of the root
that the OU is in). This string is followed by a second “-” dash
and from 8 to 32 additional lowercase letters or digits.
    """
    )
    Arn: str
    Name: str
    Type: ServiceControlPolicyTargetItemType = Field(
        default=ServiceControlPolicyTargetItemType.ACCOUNT
    )


class TagItem(OutputModels):
    Key: str
    Value: str


class ServiceControlPolicyItem(OutputModels):
    Id: str
    Arn: str
    Name: str
    Description: str
    Type: OrganizationsPolicyType = Field(
        default=OrganizationsPolicyType.SERVICE_CONTROL_POLICY
    )
    AwsManaged: bool
    Targets: list[ServiceControlPolicyTargetItem] = Field(default_factory=list)
    PolicyDocument: PolicyDocumentItem
    Tags: List[TagItem]


class ServiceControlPolicyCache(TypedDict):
    file_path: str
    policy_id: str
    arn: str
    account_id: str


class ServiceControlPolicyResourceFiles(TypedDict):
    account_id: str
    policies: list[ServiceControlPolicyCache]
