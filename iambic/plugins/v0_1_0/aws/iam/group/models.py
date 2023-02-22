from __future__ import annotations

import asyncio
from itertools import chain
from typing import Callable, Optional, Union

import botocore
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
from iambic.plugins.v0_1_0.aws.iam.group.utils import (
    apply_group_inline_policies,
    apply_group_managed_policies,
    delete_iam_group,
    get_group,
)
from iambic.plugins.v0_1_0.aws.iam.models import Path
from iambic.plugins.v0_1_0.aws.iam.policy.models import ManagedPolicyRef, PolicyDocument
from iambic.plugins.v0_1_0.aws.models import (
    ARN_RE,
    AccessModel,
    AWSAccount,
    AWSTemplate,
)
from iambic.plugins.v0_1_0.aws.utils import boto_crud_call, remove_expired_resources
from pydantic import Field, constr, validator

AWS_IAM_GROUP_TEMPLATE_TYPE = "NOQ::AWS::IAM::Group"


class PermissionBoundary(ExpiryModel, AccessModel):
    policy_arn: constr(regex=ARN_RE)

    @property
    def resource_type(self):
        return "aws:iam:permission_boundary"

    @property
    def resource_id(self):
        return self.policy_arn


class GroupProperties(BaseModel):
    group_name: str = Field(
        description="Name of the group",
    )
    path: Optional[Union[str, list[Path]]] = "/"
    managed_policies: Optional[list[ManagedPolicyRef]] = Field(
        [],
        description="Managed policy arns attached to the group",
    )
    inline_policies: Optional[list[PolicyDocument]] = Field(
        [],
        description="List of the group's inline policies",
    )

    @property
    def resource_type(self):
        return "aws:iam:group"

    @property
    def resource_id(self):
        return self.group_name

    @classmethod
    def sort_func(cls, attribute_name: str) -> Callable:
        def _sort_func(obj):
            return f"{getattr(obj, attribute_name)}!{obj.access_model_sort_weight()}"

        return _sort_func

    @validator("managed_policies")
    def sort_managed_policy_refs(cls, v: list[ManagedPolicyRef]):
        sorted_v = sorted(v, key=cls.sort_func("policy_arn"))
        return sorted_v

    @validator("inline_policies")
    def sort_inline_policies(cls, v: list[PolicyDocument]):
        sorted_v = sorted(v, key=cls.sort_func("policy_name"))
        return sorted_v


class GroupTemplate(AWSTemplate, AccessModel):
    template_type = AWS_IAM_GROUP_TEMPLATE_TYPE
    properties: GroupProperties = Field(
        description="Properties of the group",
    )

    def _is_iambic_import_only(self, aws_account: AWSAccount):
        return (
            "aws-service-group" in self.properties.path
            or aws_account.iambic_managed == IambicManaged.IMPORT_ONLY
            or self.iambic_managed == IambicManaged.IMPORT_ONLY
        )

    async def _apply_to_account(  # noqa: C901
        self, aws_account: AWSAccount, context: ExecutionContext
    ) -> AccountChangeDetails:
        boto3_session = await aws_account.get_boto3_session()
        client = boto3_session.client(
            "iam", config=botocore.client.Config(max_pool_connections=50)
        )
        self = await remove_expired_resources(
            self, self.resource_type, self.resource_id
        )
        account_group = self.apply_resource_dict(aws_account, context)

        self = await remove_expired_resources(
            self, self.resource_type, self.resource_id
        )
        group_name = account_group["GroupName"]
        account_change_details = AccountChangeDetails(
            account=str(aws_account),
            resource_id=group_name,
            new_value=dict(**account_group),
            proposed_changes=[],
        )
        log_params = dict(
            resource_type=self.resource_type,
            resource_id=group_name,
            account=str(aws_account),
        )
        iambic_import_only = self._is_iambic_import_only(aws_account)

        current_group = await get_group(group_name, client)
        if current_group:
            account_change_details.current_value = {
                **current_group
            }  # Create a new dict

        deleted = self.get_attribute_val_for_account(aws_account, "deleted", False)
        if isinstance(deleted, list):
            deleted = deleted[0].deleted

        if deleted:
            if current_group:
                account_change_details.new_value = None
                account_change_details.proposed_changes.append(
                    ProposedChange(
                        change_type=ProposedChangeType.DELETE,
                        resource_id=group_name,
                        resource_type=self.resource_type,
                    )
                )
                log_str = "Active resource found with deleted=false."
                if context.execute and not iambic_import_only:
                    log_str = f"{log_str} Deleting resource..."
                log.info(log_str, **log_params)

                if context.execute:
                    await delete_iam_group(group_name, client, log_params)

            return account_change_details

        group_exists = bool(current_group)
        inline_policies = account_group.pop("InlinePolicies", [])
        managed_policies = account_group.pop("ManagedPolicies", [])
        existing_inline_policies = current_group.pop("InlinePolicies", [])
        existing_managed_policies = current_group.pop("ManagedPolicies", [])
        tasks = []
        try:
            if group_exists:
                tasks.extend([])

                supported_update_keys = ["Description", "MaxSessionDuration"]
                update_resource_log_params = {**log_params}
                update_group_params = {}
                for k in supported_update_keys:
                    if account_group.get(k) is not None and account_group.get(
                        k
                    ) != current_group.get(k):
                        update_resource_log_params[k] = dict(
                            old_value=current_group.get(k),
                            new_value=account_group.get(k),
                        )
                        update_group_params[k] = current_group.get(k)

                if update_group_params:
                    log_str = "Out of date resource found."
                    if context.execute:
                        log.info(
                            f"{log_str} Updating resource...",
                            **update_resource_log_params,
                        )
                        tasks.append(
                            boto_crud_call(
                                client.update_group,
                                RoleName=group_name,
                                **{
                                    k: account_group.get(k)
                                    for k in supported_update_keys
                                },
                            )
                        )
                    else:
                        log.info(log_str, **update_resource_log_params)
                        account_change_details.proposed_changes.append(
                            ProposedChange(
                                change_type=ProposedChangeType.UPDATE,
                                resource_id=group_name,
                                resource_type=self.resource_type,
                            )
                        )
            else:
                account_change_details.proposed_changes.append(
                    ProposedChange(
                        change_type=ProposedChangeType.CREATE,
                        resource_id=group_name,
                        resource_type=self.resource_type,
                    )
                )
                log_str = "New resource found in code."
                if not context.execute:
                    log.info(log_str, **log_params)
                    # Exit now because apply functions won't work if resource doesn't exist
                    return account_change_details

                log_str = f"{log_str} Creating resource..."
                log.info(log_str, **log_params)
                await boto_crud_call(client.create_group, **account_group)
        except Exception as e:
            log.error("Unable to generate tasks for resource", error=e, **log_params)
            return account_change_details

        tasks.extend(
            [
                apply_group_managed_policies(
                    group_name,
                    client,
                    managed_policies,
                    existing_managed_policies,
                    log_params,
                    context,
                ),
                apply_group_inline_policies(
                    group_name,
                    client,
                    inline_policies,
                    existing_inline_policies,
                    log_params,
                    context,
                ),
            ]
        )
        try:
            changes_made = await asyncio.gather(*tasks)
        except Exception as e:
            log.exception("Unable to apply changes to resource", error=e, **log_params)
            return account_change_details
        if any(changes_made):
            account_change_details.proposed_changes.extend(
                list(chain.from_iterable(changes_made))
            )

        if context.execute:
            if self.deleted:
                self.delete()
            self.write()
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
