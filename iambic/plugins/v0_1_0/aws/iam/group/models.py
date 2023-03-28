from __future__ import annotations

import asyncio
from typing import Callable, Optional, Union

import botocore
from pydantic import Field, validator

from iambic.core.context import ctx
from iambic.core.iambic_enum import Command, IambicManaged
from iambic.core.logger import log
from iambic.core.models import (
    AccountChangeDetails,
    BaseModel,
    ProposedChange,
    ProposedChangeType,
)
from iambic.core.utils import plugin_apply_wrapper
from iambic.plugins.v0_1_0.aws.iam.group.utils import (
    apply_group_inline_policies,
    apply_group_managed_policies,
    delete_iam_group,
    get_group,
)
from iambic.plugins.v0_1_0.aws.iam.models import Path
from iambic.plugins.v0_1_0.aws.iam.policy.models import ManagedPolicyRef, PolicyDocument
from iambic.plugins.v0_1_0.aws.models import AccessModel, AwsAccount, AWSTemplate
from iambic.plugins.v0_1_0.aws.utils import boto_crud_call, remove_expired_resources

AWS_IAM_GROUP_TEMPLATE_TYPE = "NOQ::AWS::IAM::Group"


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

    @validator("path")
    def sort_path(cls, v: list[Path]):
        if not isinstance(v, list):
            return v
        sorted_v = sorted(v, key=lambda d: d.access_model_sort_weight())
        return sorted_v


class AwsIamGroupTemplate(AWSTemplate, AccessModel):
    template_type = AWS_IAM_GROUP_TEMPLATE_TYPE
    owner: Optional[str] = Field(None, description="Owner of the group")
    properties: GroupProperties = Field(
        description="Properties of the group",
    )

    def _is_iambic_import_only(self, aws_account: AwsAccount):
        return (
            "aws-service-group" in self.properties.path
            or aws_account.iambic_managed == IambicManaged.IMPORT_ONLY
            or self.iambic_managed == IambicManaged.IMPORT_ONLY
        )

    async def _apply_to_account(  # noqa: C901
        self, aws_account: AwsAccount
    ) -> AccountChangeDetails:
        boto3_session = await aws_account.get_boto3_session()
        client = boto3_session.client(
            "iam", config=botocore.client.Config(max_pool_connections=50)
        )
        self = await remove_expired_resources(
            self, self.resource_type, self.resource_id
        )
        account_group = self.apply_resource_dict(aws_account)

        self = await remove_expired_resources(
            self, self.resource_type, self.resource_id
        )
        group_name = account_group["GroupName"]
        account_change_details = AccountChangeDetails(
            account=str(aws_account),
            resource_id=group_name,
            new_value=dict(**account_group),
            proposed_changes=[],
            exceptions_seen=[],
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

            if ctx.command == Command.CONFIG_DISCOVERY:
                # Don't overwrite a resource during config discovery
                account_change_details.new_value = {}
                return account_change_details

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
                if ctx.execute and not iambic_import_only:
                    log_str = f"{log_str} Deleting resource..."
                log.info(log_str, **log_params)

                if ctx.execute:
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

                supported_update_keys = ["Path", "GroupName"]
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
                        update_group_params[f"New{k}"] = account_group.get(k)

                if update_group_params:
                    log_str = "Out of date resource found."
                    proposed_changes = [
                        ProposedChange(
                            change_type=ProposedChangeType.UPDATE,
                            resource_id=group_name,
                            resource_type=self.resource_type,
                        )
                    ]
                    if ctx.execute:
                        log.info(
                            f"{log_str} Updating resource...",
                            **update_resource_log_params,
                        )
                        apply_awaitable = boto_crud_call(
                            client.update_group,
                            RoleName=group_name,
                            **update_group_params,
                        )
                        tasks.append(
                            plugin_apply_wrapper(apply_awaitable, proposed_changes)
                        )
                    else:
                        log.info(log_str, **update_resource_log_params)
                        account_change_details.proposed_changes.extend(proposed_changes)
            else:
                account_change_details.proposed_changes.append(
                    ProposedChange(
                        change_type=ProposedChangeType.CREATE,
                        resource_id=group_name,
                        resource_type=self.resource_type,
                    )
                )
                log_str = "New resource found in code."
                if not ctx.execute:
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
                ),
                apply_group_inline_policies(
                    group_name,
                    client,
                    inline_policies,
                    existing_inline_policies,
                    log_params,
                ),
            ]
        )
        try:
            results: list[list[ProposedChange]] = await asyncio.gather(
                *tasks, return_exceptions=True
            )

            # separate out the success versus failure calls
            exceptions: list[ProposedChange] = []
            changes_made: list[ProposedChange] = []
            for result in results:
                for r in result:
                    if isinstance(r, ProposedChange):
                        if len(r.exceptions_seen) == 0:
                            changes_made.append(r)
                        else:
                            exceptions.append(r)

        except Exception as e:
            log.exception("Unable to apply changes to resource", error=e, **log_params)
            return account_change_details
        if any(changes_made):
            account_change_details.proposed_changes.extend(changes_made)
        if any(exceptions):
            account_change_details.exceptions_seen.extend(exceptions)

        if ctx.execute:
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
