from __future__ import annotations

import asyncio
import json
from itertools import chain
from typing import Callable, Optional, Union

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
from iambic.core.utils import plugin_apply_wrapper
from iambic.plugins.v0_1_0.aws.iam.models import (
    MaxSessionDuration,
    Path,
    PermissionBoundary,
)
from iambic.plugins.v0_1_0.aws.iam.policy.models import (
    AssumeRolePolicyDocument,
    ManagedPolicyRef,
    PolicyDocument,
)
from iambic.plugins.v0_1_0.aws.iam.role.utils import (
    apply_role_inline_policies,
    apply_role_managed_policies,
    apply_role_permission_boundary,
    apply_role_tags,
    delete_iam_role,
    get_role,
    update_assume_role_policy,
)
from iambic.plugins.v0_1_0.aws.models import (
    AccessModel,
    AWSAccount,
    AWSTemplate,
    Description,
    Tag,
)
from iambic.plugins.v0_1_0.aws.utils import boto_crud_call

AWS_IAM_ROLE_TEMPLATE_TYPE = "NOQ::AWS::IAM::Role"


class RoleAccess(ExpiryModel, AccessModel):
    users: list[str] = Field(
        [],
        description="List of users who can assume into the role",
    )
    groups: list[str] = Field(
        [],
        description="List of groups. Users in one or more of the groups can assume into the role",
    )

    @property
    def resource_type(self):
        return "aws:iam:role:access_rule"

    @property
    def resource_id(self):
        return


class RoleProperties(BaseModel):
    role_name: str = Field(
        description="Name of the role",
    )
    description: Optional[Union[str, list[Description]]] = Field(
        "",
        description="Description of the role",
    )
    max_session_duration: Optional[Union[int, list[MaxSessionDuration]]] = 3600
    path: Optional[Union[str, list[Path]]] = "/"
    permissions_boundary: Optional[
        Union[None, PermissionBoundary, list[PermissionBoundary]]
    ] = None
    assume_role_policy_document: Optional[
        Union[None, list[AssumeRolePolicyDocument], AssumeRolePolicyDocument]
    ] = Field(
        [],
        description="Who can assume the Role",
    )
    tags: Optional[list[Tag]] = Field(
        [],
        description="List of tags attached to the role",
    )
    managed_policies: Optional[list[ManagedPolicyRef]] = Field(
        [],
        description="Managed policy arns attached to the role",
    )
    inline_policies: Optional[list[PolicyDocument]] = Field(
        [],
        description="List of the role's inline policies",
    )

    @property
    def resource_type(self):
        return "aws:iam:role"

    @property
    def resource_id(self):
        return self.role_name

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

    @validator("tags")
    def sort_tags(cls, v: list[Tag]):
        sorted_v = sorted(v, key=cls.sort_func("key"))
        return sorted_v

    @validator("assume_role_policy_document")
    def sort_assume_role_policy_documents(cls, v: list[AssumeRolePolicyDocument]):
        if not isinstance(v, list):
            return v
        sorted_v = sorted(v, key=lambda d: d.access_model_sort_weight())
        return sorted_v

    @validator("max_session_duration")
    def sort_max_session_duration(cls, v: list[MaxSessionDuration]):
        if not isinstance(v, list):
            return v
        sorted_v = sorted(v, key=lambda d: d.access_model_sort_weight())
        return sorted_v

    @validator("permissions_boundary")
    def sort_permissions_boundary(cls, v: list[PermissionBoundary]):
        if not isinstance(v, list):
            return v
        sorted_v = sorted(v, key=lambda d: d.access_model_sort_weight())
        return sorted_v

    @validator("path")
    def sort_path(cls, v: list[Path]):
        if not isinstance(v, list):
            return v
        sorted_v = sorted(v, key=lambda d: d.access_model_sort_weight())
        return sorted_v

    @validator("description")
    def sort_description(cls, v: list[Description]):
        if not isinstance(v, list):
            return v
        sorted_v = sorted(v, key=lambda d: d.access_model_sort_weight())
        return sorted_v


class AwsIamRoleTemplate(AWSTemplate, AccessModel):
    template_type = AWS_IAM_ROLE_TEMPLATE_TYPE
    owner: Optional[str] = Field(None, description="Owner of the role")
    properties: RoleProperties = Field(
        description="Properties of the role",
    )
    access_rules: Optional[list[RoleAccess]] = Field(
        [],
        description="Used to define users and groups who can access the role via Noq credential brokering",
    )

    @validator("access_rules")
    def sort_access_rules(cls, v: list[RoleAccess]):
        sorted_v = sorted(v, key=lambda d: d.access_model_sort_weight())
        return sorted_v

    def _apply_resource_dict(self, aws_account: AWSAccount = None) -> dict:
        response = super(AwsIamRoleTemplate, self)._apply_resource_dict(aws_account)
        response.pop("RoleAccess", None)
        if "Tags" not in response:
            response["Tags"] = []

        # Ensure only 1 of the following objects
        # TODO: Have this handled in a cleaner way. Maybe via an attribute on a pydantic field
        if assume_role_policy := response.pop("AssumeRolePolicyDocument", []):
            if isinstance(assume_role_policy, list):
                assume_role_policy = assume_role_policy[0]
            response["AssumeRolePolicyDocument"] = assume_role_policy

        if permissions_boundary := response.pop("PermissionsBoundary", []):
            if isinstance(permissions_boundary, list):
                permissions_boundary = permissions_boundary[0]
            response["PermissionsBoundary"] = permissions_boundary

        if isinstance(response.get("Description"), list):
            response["Description"] = response["Description"][0]["Description"]

        if isinstance(response.get("MaxSessionDuration"), list):
            response["MaxSessionDuration"] = response["MaxSessionDuration"][0][
                "MaxSessionDuration"
            ]

        return response

    def _is_iambic_import_only(self):
        return "aws-service-role" in self.properties.path

    async def _apply_to_account(  # noqa: C901
        self, aws_account: AWSAccount
    ) -> AccountChangeDetails:
        client = await aws_account.get_boto3_client("iam")
        account_role = self.apply_resource_dict(aws_account)
        role_name = account_role["RoleName"]
        account_change_details = AccountChangeDetails(
            account=str(aws_account),
            resource_id=role_name,
            resource_type=self.resource_type,
            new_value=dict(**account_role),
            proposed_changes=[],
            exceptions_seen=[],
        )
        if self._is_iambic_import_only():
            # Don't apply changes to aws-service-roles
            return account_change_details

        log_params = dict(
            resource_type=self.resource_type,
            resource_id=role_name,
            account=str(aws_account),
        )
        deleted = self.get_attribute_val_for_account(aws_account, "deleted", False)
        current_role = await get_role(
            role_name, client, include_policies=bool(not deleted)
        )
        if current_role:
            account_change_details.current_value = {**current_role}  # Create a new dict

            if ctx.command == Command.CONFIG_DISCOVERY:
                # Don't overwrite a resource during config discovery
                account_change_details.new_value = {}
                return account_change_details

        deleted = self.get_attribute_val_for_account(aws_account, "deleted", False)
        if isinstance(deleted, list):
            deleted = deleted[0].deleted

        if deleted:
            if current_role:
                account_change_details.new_value = None
                proposed_changes = [
                    ProposedChange(
                        change_type=ProposedChangeType.DELETE,
                        resource_id=role_name,
                        resource_type=self.resource_type,
                    )
                ]
                log_str = "Active resource found with deleted=false."
                if ctx.execute:
                    log_str = f"{log_str} Deleting resource..."
                log.debug(log_str, **log_params)

                if ctx.execute:
                    apply_awaitable = delete_iam_role(role_name, client, log_params)
                    proposed_changes = await plugin_apply_wrapper(
                        apply_awaitable, proposed_changes
                    )

                account_change_details.extend_changes(proposed_changes)

            return account_change_details

        role_exists = bool(current_role)
        inline_policies = account_role.pop("InlinePolicies", [])
        managed_policies = account_role.pop("ManagedPolicies", [])
        existing_inline_policies = current_role.pop("InlinePolicies", [])
        existing_managed_policies = current_role.pop("ManagedPolicies", [])
        tasks = []
        if role_exists:
            tasks.extend(
                [
                    apply_role_tags(
                        role_name,
                        client,
                        account_role["Tags"],
                        current_role.get("Tags", []),
                        log_params,
                    ),
                    update_assume_role_policy(
                        role_name,
                        client,
                        account_role.pop("AssumeRolePolicyDocument", {}),
                        current_role["AssumeRolePolicyDocument"],
                        log_params,
                    ),
                    apply_role_permission_boundary(
                        role_name,
                        client,
                        account_role.get("PermissionsBoundary", {}),
                        current_role.get("PermissionsBoundary", {}),
                        log_params,
                    ),
                ]
            )

            supported_update_keys = ["Description", "MaxSessionDuration"]
            update_resource_log_params = {**log_params}
            update_role_params = {}
            for k in supported_update_keys:
                if account_role.get(k) is not None and account_role.get(
                    k
                ) != current_role.get(k):
                    update_resource_log_params[k] = dict(
                        old_value=current_role.get(k), new_value=account_role.get(k)
                    )
                    update_role_params[k] = current_role.get(k)

            if update_role_params:
                log_str = "Out of date resource found."
                if ctx.execute:
                    log.debug(
                        f"{log_str} Updating resource...",
                        **update_resource_log_params,
                    )

                    async def update_role():
                        exceptions = []
                        try:
                            await boto_crud_call(
                                client.update_role,
                                RoleName=role_name,
                                **{
                                    k: account_role.get(k)
                                    for k in supported_update_keys
                                },
                            )
                        except Exception as e:
                            exceptions.append(str(e))
                        return [
                            ProposedChange(
                                change_type=ProposedChangeType.UPDATE,
                                resource_id=role_name,
                                resource_type=self.resource_type,
                                exceptions_seen=exceptions,
                            )
                        ]

                    tasks.append(update_role())
                else:
                    log.debug(log_str, **update_resource_log_params)
                    account_change_details.proposed_changes.append(
                        ProposedChange(
                            change_type=ProposedChangeType.UPDATE,
                            resource_id=role_name,
                            resource_type=self.resource_type,
                        )
                    )
        else:
            proposed_changes = [
                ProposedChange(
                    change_type=ProposedChangeType.CREATE,
                    resource_id=role_name,
                    resource_type=self.resource_type,
                )
            ]
            log_str = "New resource found in code."
            if not ctx.execute:
                # Exit now because apply functions won't work if resource doesn't exist
                log.debug(log_str, **log_params)
                account_change_details.extend_changes(proposed_changes)
                return account_change_details

            log.debug(f"{log_str} Creating resource...", **log_params)
            account_role["AssumeRolePolicyDocument"] = json.dumps(
                account_role["AssumeRolePolicyDocument"]
            )
            if account_role.get("PermissionsBoundary"):
                account_role["PermissionsBoundary"] = account_role[
                    "PermissionsBoundary"
                ]["PolicyArn"]

            apply_awaitable = boto_crud_call(client.create_role, **account_role)
            account_change_details.extend_changes(
                await plugin_apply_wrapper(apply_awaitable, proposed_changes)
            )

        tasks.extend(
            [
                apply_role_managed_policies(
                    role_name,
                    client,
                    managed_policies,
                    existing_managed_policies,
                    log_params,
                ),
                apply_role_inline_policies(
                    role_name,
                    client,
                    inline_policies,
                    existing_inline_policies,
                    log_params,
                ),
            ]
        )

        changes_made = await asyncio.gather(*tasks)
        if any(changes_made):
            account_change_details.extend_changes(
                list(chain.from_iterable(changes_made))
            )

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

        return account_change_details

    @classmethod
    def iambic_specific_knowledge(cls) -> set[str]:
        return {"access_rules", "file_path", "iambic_managed"}
