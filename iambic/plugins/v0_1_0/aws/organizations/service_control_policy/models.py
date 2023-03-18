from __future__ import annotations

import asyncio
import json
from typing import Callable, List, Optional, Union

import botocore
from jinja2 import BaseLoader, Environment
from pydantic import Field, constr, validator

from iambic.core.context import ExecutionContext, ctx
from iambic.core.iambic_enum import Command, IambicManaged
from iambic.core.logger import log
from iambic.core.models import (
    AccountChangeDetails,
    BaseModel,
    ExpiryModel,
    ProposedChange,
    ProposedChangeType,
)
from iambic.core.utils import sanitize_string
from iambic.plugins.v0_1_0.aws.iam.models import Path
from iambic.plugins.v0_1_0.aws.iam.policy.models import PolicyStatement
from iambic.plugins.v0_1_0.aws.models import (
    ARN_RE,
    AccessModel,
    AWSAccount,
    AWSTemplate,
    Description,
    Tag,
)
from iambic.plugins.v0_1_0.aws.organizations.service_control_policy.utils import (
    apply_update_service_control_policy,
    delete_service_control_policy,
    get_service_control_policy,
)
from iambic.plugins.v0_1_0.aws.utils import boto_crud_call

AWS_SCP_POLICY_TEMPLATE_TYPE = "NOQ::AWS::Organizations::ServiceControlPolicy"


class ServiceControlPolicyDocument(AccessModel):
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
        valid_characters_re = r"[\w_+=,.@-]"
        variables = [sanitize_string(v, valid_characters_re) for v in variables]
        data = rtemplate.render(**variables)
        return json.loads(data)

    @property
    def resource_type(self):
        return "aws:organizations:scp_policy:policy_document"

    @property
    def resource_id(self):
        return "N/A"


class ServiceControlPolicyProperties(BaseModel):
    policy_name: str = Field(
        description="The name of the service control policy.",
    )
    description: Optional[Union[str, list[Description]]] = Field(
        "",
        description="Description of the service control policy",
    )
    policy_document: Union[
        ServiceControlPolicyDocument, List[ServiceControlPolicyDocument]
    ]
    tags: Optional[List[Tag]] = Field(
        [],
        description="List of tags attached to the service control policy",
    )

    @property
    def resource_type(self):
        return "aws:organizations:scp_policy:properties"

    @property
    def resource_id(self):
        return self.policy_name

    @validator("tags")
    def sort_tags(cls, v: list[Tag]):
        sorted_v = sorted(v, key=cls.sort_func("key"))
        return sorted_v


class ServiceControlPolicyTemplate(AWSTemplate, AccessModel):
    template_type = AWS_SCP_POLICY_TEMPLATE_TYPE
    properties: ServiceControlPolicyProperties = Field(
        description="The properties of the service control policy",
    )

    def get_arn_for_account(self, aws_account: AWSAccount) -> str:
        policy_name = self.properties.policy_name
        return f"arn:{aws_account.partition.value}:organizations::{aws_account.account_id}:policy/O-1234567890/SCP-{policy_name}"

    def _apply_resource_dict(
        self, aws_account: AWSAccount = None, context: ExecutionContext = None
    ) -> dict:
        resource_dict = super()._apply_resource_dict(aws_account, context)
        resource_dict["Arn"] = self.get_arn_for_account(aws_account)
        return resource_dict

    async def _apply_to_account(
        self, aws_account: AWSAccount, context: ExecutionContext
    ) -> AccountChangeDetails:
        boto3_session = await aws_account.get_boto3_session()
        client = boto3_session.client(
            "organizations", config=botocore.client.Config(max_pool_connections=50)
        )
        account_policy = self.apply_resource_dict(aws_account, context)
        policy_name = account_policy["PolicyName"]
        account_change_details = AccountChangeDetails(
            account=str(aws_account),
            resource_id=policy_name,
            new_value=dict(**account_policy),
            proposed_changes=[],
            exceptions_seen=[],
        )
        log_params = dict(
            resource_type=self.resource_type,
            resource_id=policy_name,
            account=str(aws_account),
        )
        policy_arn = account_policy.pop("Arn")
        current_policy = await get_service_control_policy(client, policy_arn)
        if current_policy:
            account_change_details.current_value = {**current_policy}

            if context.command == Command.CONFIG_DISCOVERY:
                # Don't overwrite a resource during config discovery
                account_change_details.new_value = {}
                return account_change_details

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
                log_str = (
                    "Active resource found with deleted=false. Deleting resource..."
                )
                await delete_service_control_policy(client, policy_arn, log_params)

            return account_change_details

        if current_policy:
            tasks = [
                apply_update_service_control_policy(
                    client,
                    policy_arn,
                    json.loads(account_policy["PolicyDocument"]),
                    current_policy["PolicyDocument"],
                    log_params,
                    context,
                ),
                apply_service_control_policy_tags(
                    client,
                    policy_arn,
                    account_policy.get("Tags", []),
                    current_policy.get("Tags", []),
                    log_params,
                    context,
                ),
            ]

            results: list[list[ProposedChange]] = await asyncio.gather(*tasks)

            exceptions: list[ProposedChange] = []
            changes_made: list[ProposedChange] = []
            for result in results:
                for r in result:
                    if isinstance(r, ProposedChange):
                        if len(r.exceptions_seen) == 0:
                            changes_made.append(r)
                        else:
                            exceptions.append(r)

            if any(changes_made):
                account_change_details.proposed_changes.extend(changes_made)
            if any(exceptions):
                account_change_details.exceptions_seen.extend(exceptions)
        else:
            account_change_details.proposed_changes.append(
                ProposedChange(
                    change_type=ProposedChangeType.CREATE,
                    resource_id=policy_name,
                    resource_type=self.resource_type,
                )
            )
            log_str = "New resource found in code. Creating resource..."
            await boto_crud_call(client.create_policy, **account_policy)

        log.debug(
            "Successfully finished execution on account for resource",
            changes_made=bool(account_change_details.proposed_changes),
            **log_params,
        )

        return account_change_details

    @property
    def resource_type(self):
        return "aws:organizations:scp_policy"

    @property
    def resource_id(self):
        return self.properties.policy_name
