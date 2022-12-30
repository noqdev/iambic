from __future__ import annotations

import asyncio
import json
from itertools import chain
from typing import List, Optional, Union

import botocore
from jinja2 import BaseLoader, Environment
from pydantic import Field, constr

from iambic.aws.iam.models import Path
from iambic.aws.iam.policy.utils import (
    apply_managed_policy_tags,
    delete_managed_policy,
    get_managed_policy,
    update_managed_policy,
)
from iambic.aws.models import (
    ARN_RE,
    AccessModel,
    AWSAccount,
    AWSTemplate,
    Description,
    Tag,
)
from iambic.core.context import ExecutionContext
from iambic.core.iambic_enum import IambicManaged
from iambic.core.logger import log
from iambic.core.models import (
    AccountChangeDetails,
    BaseModel,
    ExpiryModel,
    ProposedChange,
    ProposedChangeType,
)
from iambic.core.utils import aio_wrapper


class Principal(BaseModel):
    aws: Optional[Union[str, list[str]]] = None
    service: Optional[Union[str, list[str]]] = None
    canonical_user: Optional[Union[str, list[str]]] = None
    federated: Optional[Union[str, list[str]]] = None

    def _apply_resource_dict(
        self, aws_account: AWSAccount = None, context: ExecutionContext = None
    ) -> dict:
        resource_dict = super(Principal, self)._apply_resource_dict(
            aws_account, context
        )
        if aws_val := resource_dict.pop("aws", resource_dict.pop("Aws", None)):
            resource_dict["AWS"] = aws_val
        return resource_dict

    @property
    def resource_type(self) -> str:
        return "aws:iam:policy_principal"

    @property
    def resource_id(self) -> str:
        return self.service or self.canonical_user or self.federated or self.aws


class ConditionalStatement(BaseModel):
    for_all_values: Optional[bool] = None
    for_any_values: Optional[bool] = None


class Condition(BaseModel):
    """TODO: Finish this.

    I put in a pin it because it became obvious this will be a large undertaking.
    The problem stems from the way conditions are structured.

    Take string_equals: Optional[dict] = None for example
    For this one attribute it also requires the following:
        for_all_values__string_equals
        for_any_values__string_equals
        for_all_values__string_equals__if_exists
        for_any_values__string_equals__if_exists
    On top of that we still need to add clarity on what the supported keys are.

    For more info on conditions:
    https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_condition.html

    """

    # Key = service/resource_type
    # Value = resource_value , list[resource_value]

    # String conditionals
    string_equals: Optional[dict] = None
    string_not_equals: Optional[dict] = None
    string_equals_ignore_case: Optional[dict] = None
    string_like: Optional[dict] = None
    string_not_like: Optional[dict] = None

    # Numeric Conditionals
    numeric_equals: Optional[dict] = None
    numeric_not_equals: Optional[dict] = None
    numeric_less_than: Optional[dict] = None
    numeric_less_than_equals: Optional[dict] = None
    numeric_greater_than: Optional[dict] = None
    numeric_greater_than_equals: Optional[dict] = None

    # Date Conditionals
    date_equals: Optional[dict] = None
    date_not_equals: Optional[dict] = None
    date_less_than: Optional[dict] = None
    date_less_than_equals: Optional[dict] = None
    date_greater_than: Optional[dict] = None
    date_greater_than_equals: Optional[dict] = None

    # IP Addr Conditionals
    ip_address: Optional[dict] = None
    not_ip_address: Optional[dict] = None

    # ARN Conditionals
    arn_equals: Optional[dict] = None
    arn_like: Optional[dict] = None
    arn_not_equals: Optional[dict] = None
    arn_not_like: Optional[dict] = None

    # Null Conditional
    null: Optional[dict] = None

    # Boolean conditional
    bool: Optional[dict] = None


class PolicyStatement(AccessModel, ExpiryModel):
    effect: str = Field(..., description="Allow | Deny")
    principal: Optional[Union[Principal, str]] = None
    not_principal: Optional[Union[Principal, str]] = None
    action: Optional[Union[List[str], str]] = Field(
        None,
        description="A single regex or list of regexes. "
        "Values are the actions that can be performed on the resources in the policy statement",
        example="dynamodb:list*",
    )
    not_action: Optional[Union[List[str], str]] = Field(
        None,
        description="An advanced policy element that explicitly matches everything except the specified list of actions."
        "DON'T use this with effect: allow in the same statement OR policy",
    )
    resource: Optional[Union[List[str], str]] = Field(
        None,
        description="A single regex or list of regexes. Values specified are the resources the statement applies to",
    )
    not_resource: Optional[Union[List[str], str]] = Field(
        None,
        description="An advanced policy element that explicitly matches every resource except those specified."
        "DON'T use this with effect: allow and action: '*'",
    )
    condition: Optional[dict] = Field(
        None,
        description="An optional set of conditions to determine of the policy applies to a resource.",
    )
    sid: Optional[str] = Field(
        None,
        description="The Policy Statement ID.",
    )

    @property
    def resource_type(self):
        return "aws:iam:policy_statement"

    @property
    def resource_id(self):
        return self.sid


class AssumeRolePolicyDocument(AccessModel):
    version: Optional[str] = None
    statement: Optional[List[PolicyStatement]] = None

    @property
    def resource_type(self) -> str:
        return "aws:iam:assume_role_policy_document"

    @property
    def resource_id(self) -> str:
        return ""


class PolicyDocument(AccessModel, ExpiryModel):
    policy_name: str = Field(
        description="The name of the policy.",
    )
    version: Optional[str] = None
    statement: Optional[List[PolicyStatement]] = Field(
        None,
        description="List of policy statements",
    )

    @property
    def resource_type(self):
        return "aws:policy_document"

    @property
    def resource_id(self):
        return self.policy_name


class ManagedPolicyDocument(AccessModel):
    version: Optional[str] = None
    statement: Optional[List[PolicyStatement]] = Field(
        None,
        description="List of policy statements",
    )

    def _apply_resource_dict(
        self, aws_account: AWSAccount = None, context: ExecutionContext = None
    ) -> str:
        resource_dict = super()._apply_resource_dict(aws_account, context)
        return json.dumps(resource_dict)

    def apply_resource_dict(
        self, aws_account: AWSAccount, context: ExecutionContext
    ) -> dict:
        response = json.loads(self._apply_resource_dict(aws_account, context))
        variables = {var.key: var.value for var in aws_account.variables}
        variables["account_id"] = aws_account.account_id
        variables["account_name"] = aws_account.account_name

        rtemplate = Environment(loader=BaseLoader()).from_string(json.dumps(response))
        data = rtemplate.render(**variables)
        return json.loads(data)

    @property
    def resource_type(self):
        return "aws:iam:managed_policy:policy_document"

    @property
    def resource_id(self):
        return


class ManagedPolicyProperties(BaseModel):
    policy_name: str = Field(
        description="The name of the policy.",
    )
    path: Optional[Union[str, List[Path]]] = "/"
    description: Optional[Union[str, list[Description]]] = Field(
        "",
        description="Description of the role",
    )
    policy_document: Union[ManagedPolicyDocument, List[ManagedPolicyDocument]]
    tags: Optional[List[Tag]] = Field(
        [],
        description="List of tags attached to the role",
    )


class ManagedPolicyTemplate(AWSTemplate, AccessModel):
    template_type = "NOQ::IAM::ManagedPolicy"
    identifier: str
    properties: ManagedPolicyProperties = Field(
        description="The properties of the managed policy",
    )

    def _is_iambic_import_only(
        self, aws_account: AWSAccount, context: ExecutionContext
    ):
        return (
            aws_account.iambic_managed == IambicManaged.IMPORT_ONLY
            or self.iambic_managed == IambicManaged.IMPORT_ONLY
            or context.eval_only
        )

    def _apply_resource_dict(
        self, aws_account: AWSAccount = None, context: ExecutionContext = None
    ) -> dict:
        resource_dict = super()._apply_resource_dict(aws_account, context)
        resource_dict[
            "Arn"
        ] = f"arn:aws:iam::{aws_account.account_id}:policy{resource_dict['Path']}{resource_dict['PolicyName']}"
        return resource_dict

    async def _apply_to_account(
        self, aws_account: AWSAccount, context: ExecutionContext
    ) -> AccountChangeDetails:
        boto3_session = await aws_account.get_boto3_session()
        client = boto3_session.client(
            "iam", config=botocore.client.Config(max_pool_connections=50)
        )
        account_policy = self.apply_resource_dict(aws_account, context)
        policy_name = account_policy["PolicyName"]
        account_change_details = AccountChangeDetails(
            account=str(aws_account),
            resource_id=policy_name,
            new_value=dict(**account_policy),
            proposed_changes=[],
        )
        log_params = dict(
            resource_type=self.resource_type,
            resource_id=policy_name,
            account=str(aws_account),
        )
        is_iambic_import_only = self._is_iambic_import_only(aws_account, context)
        policy_arn = account_policy.pop("Arn")
        current_policy = await get_managed_policy(policy_arn, client)
        if current_policy:
            account_change_details.current_value = {**current_policy}

        deleted = self.get_attribute_val_for_account(aws_account, "deleted", False)
        if isinstance(deleted, list):
            deleted = deleted[0].deleted

        if deleted:
            if current_policy:
                account_change_details.new_value = None
                account_change_details.proposed_changes.append(
                    ProposedChange(
                        change_type=ProposedChangeType.DELETE,
                        resource_id=policy_name,
                        resource_type=self.resource_type,
                    )
                )
                log_str = "Active resource found with deleted=false."
                if not is_iambic_import_only:
                    log_str = f"{log_str} Deleting resource..."
                log.info(log_str, **log_params)

                if not is_iambic_import_only:
                    await delete_managed_policy(policy_arn, client)

            return account_change_details

        if current_policy:
            changes_made = await asyncio.gather(
                update_managed_policy(
                    policy_arn,
                    client,
                    json.loads(account_policy["PolicyDocument"]),
                    current_policy["PolicyDocument"],
                    is_iambic_import_only,
                    log_params,
                    context,
                ),
                apply_managed_policy_tags(
                    policy_arn,
                    client,
                    account_policy.get("Tags", []),
                    current_policy.get("Tags", []),
                    is_iambic_import_only,
                    log_params,
                    context,
                ),
            )
            if any(changes_made):
                account_change_details.proposed_changes.extend(
                    list(chain.from_iterable(changes_made))
                )
        else:
            account_change_details.proposed_changes.append(
                ProposedChange(
                    change_type=ProposedChangeType.CREATE,
                    resource_id=policy_name,
                    resource_type=self.resource_type,
                )
            )
            log_str = "New resource found in code."
            if not is_iambic_import_only:
                log_str = f"{log_str} Creating resource..."
                await aio_wrapper(client.create_policy, **account_policy)
            log.info(log_str, **log_params)

        if not is_iambic_import_only:
            log.debug(
                "Successfully finished execution on account for resource",
                changes_made=bool(account_change_details.proposed_changes),
                **log_params,
            )
        else:
            log.debug(
                "Successfully finished scanning for drift on account for resource",
                requires_changes=bool(account_change_details.proposed_changes),
                **log_params,
            )

        return account_change_details

    @property
    def resource_type(self):
        return "aws:iam:managed_policy"

    @property
    def resource_id(self):
        return self.properties.policy_name


class ManagedPolicyRef(AccessModel, ExpiryModel):
    policy_arn: constr(regex=ARN_RE)

    @property
    def resource_type(self):
        return "aws:iam:managed_policy"

    @property
    def resource_id(self):
        return self.policy_arn
