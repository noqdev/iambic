from __future__ import annotations

import asyncio
from itertools import chain
from typing import Any, Callable, Optional, Union

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
from iambic.core.utils import plugin_apply_wrapper, remove_expired_resources
from iambic.plugins.v0_1_0.aws.iam.models import Path, PermissionBoundary
from iambic.plugins.v0_1_0.aws.iam.policy.models import ManagedPolicyRef, PolicyDocument
from iambic.plugins.v0_1_0.aws.iam.user.utils import (
    apply_user_groups,
    apply_user_inline_policies,
    apply_user_managed_policies,
    apply_user_permission_boundary,
    apply_user_tags,
    delete_iam_user,
    get_user,
)
from iambic.plugins.v0_1_0.aws.models import AccessModel, AWSAccount, AWSTemplate, Tag
from iambic.plugins.v0_1_0.aws.utils import boto_crud_call

AWS_IAM_USER_TEMPLATE_TYPE = "NOQ::AWS::IAM::User"


class Group(ExpiryModel, AccessModel):
    group_name: str

    # All excluded fields are populated by the API and not required in the template
    # We are not tracking those, but we do allow them to be imported in order to
    # pass validation.
    arn: Optional[str] = Field("", description="ARN of the group", exclude=True)
    create_date: Optional[str] = Field(
        "", description="Date the group was created", exclude=True
    )
    group_id: Optional[str] = Field("", description="ID of the group", exclude=True)
    path: Optional[str] = Field("", description="Path of the group", exclude=True)
    extra: Any = Field(None, description="Extra attributes to store", exclude=True)

    @property
    def resource_type(self):
        return "aws:iam:group"

    @property
    def resource_id(self):
        return self.group_name


class UserProperties(BaseModel):
    user_name: str = Field(
        description="Name of the user",
    )
    path: Optional[Union[str, list[Path]]] = "/"
    permissions_boundary: Optional[
        Union[None, PermissionBoundary, list[PermissionBoundary]]
    ] = None
    tags: Optional[list[Tag]] = Field(
        [],
        description="List of tags attached to the user",
    )
    groups: Optional[list[Group]] = Field(
        [],
        description="List of groups the user is a member of",
    )
    managed_policies: Optional[list[ManagedPolicyRef]] = Field(
        [],
        description="Managed policy arns attached to the user",
    )
    inline_policies: Optional[list[PolicyDocument]] = Field(
        [],
        description="List of the user's inline policies",
    )

    @property
    def resource_type(self):
        return "aws:iam:user"

    @property
    def resource_id(self):
        return self.user_name

    @classmethod
    def sort_func(cls, attribute_name: str) -> Callable:
        def _sort_func(obj):
            return f"{getattr(obj, attribute_name)}!{obj.access_model_sort_weight()}"

        return _sort_func

    @validator("tags")
    def sort_tags(cls, v: list[Tag]):
        sorted_v = sorted(v, key=cls.sort_func("key"))
        return sorted_v

    @validator("groups")
    def sort_groups(cls, v: list[Group]):
        sorted_v = sorted(v, key=cls.sort_func("group_name"))
        return sorted_v

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

    @validator("permissions_boundary")
    def sort_permissions_boundary(cls, v: list[PermissionBoundary]):
        if not isinstance(v, list):
            return v
        sorted_v = sorted(v, key=lambda d: d.access_model_sort_weight())
        return sorted_v


class AwsIamUserTemplate(AWSTemplate, AccessModel):
    template_type = AWS_IAM_USER_TEMPLATE_TYPE
    properties: UserProperties = Field(
        description="Properties of the user",
    )

    def _apply_resource_dict(self, aws_account: AWSAccount = None) -> dict:
        response = super(AwsIamUserTemplate, self)._apply_resource_dict(aws_account)
        if "Tags" not in response:
            response["Tags"] = []

        if permissions_boundary := response.pop("PermissionsBoundary", []):
            if isinstance(permissions_boundary, list):
                permissions_boundary = permissions_boundary[0]
            response["PermissionsBoundary"] = permissions_boundary

        if isinstance(response.get("Description"), list):
            response["Description"] = response["Description"][0]["Description"]

        return response

    async def _apply_to_account(  # noqa: C901
        self, aws_account: AWSAccount
    ) -> AccountChangeDetails:
        client = await aws_account.get_boto3_client("iam")
        self = await remove_expired_resources(
            self, self.resource_type, self.resource_id
        )
        account_user = self.apply_resource_dict(aws_account)

        user_name = account_user["UserName"]
        account_change_details = AccountChangeDetails(
            account=str(aws_account),
            resource_id=user_name,
            resource_type=self.resource_type,
            new_value=dict(**account_user),
            proposed_changes=[],
            exceptions_seen=[],
        )
        log_params = dict(
            resource_type=self.resource_type,
            resource_id=user_name,
            account=str(aws_account),
        )
        deleted = self.get_attribute_val_for_account(aws_account, "deleted", False)
        current_user = await get_user(
            user_name, client, include_policies=bool(not deleted)
        )
        if current_user:
            account_change_details.current_value = {**current_user}  # Create a new dict

            if ctx.command == Command.CONFIG_DISCOVERY:
                # Don't overwrite a resource during config discovery
                account_change_details.new_value = {}
                return account_change_details

        deleted = self.get_attribute_val_for_account(aws_account, "deleted", False)
        if isinstance(deleted, list):
            deleted = deleted[0].deleted

        if deleted:
            if current_user:
                account_change_details.new_value = None
                log_str = "Active resource found with deleted=false."
                if ctx.execute:
                    log_str = f"{log_str} Deleting resource..."
                log.debug(log_str, **log_params)

                proposed_changes = [
                    ProposedChange(
                        change_type=ProposedChangeType.DELETE,
                        resource_id=user_name,
                        resource_type=self.resource_type,
                    )
                ]
                if ctx.execute:
                    apply_awaitable = delete_iam_user(user_name, client, log_params)
                    proposed_changes = await plugin_apply_wrapper(
                        apply_awaitable, proposed_changes
                    )

                account_change_details.extend_changes(proposed_changes)

            return account_change_details

        user_exists = bool(current_user)
        inline_policies = account_user.pop("InlinePolicies", [])
        managed_policies = account_user.pop("ManagedPolicies", [])
        groups = account_user.pop("Groups", [])
        existing_inline_policies = current_user.pop("InlinePolicies", [])
        existing_managed_policies = current_user.pop("ManagedPolicies", [])
        existing_groups = current_user.pop("Groups", [])
        tasks = []

        if user_exists:
            tasks.extend(
                [
                    apply_user_tags(
                        user_name,
                        client,
                        account_user["Tags"],
                        current_user.get("Tags", []),
                        log_params,
                    ),
                    apply_user_permission_boundary(
                        user_name,
                        client,
                        account_user.get("PermissionsBoundary", {}),
                        current_user.get("PermissionsBoundary", {}),
                        log_params,
                    ),
                ]
            )

            supported_update_keys = ["Path", "UserName"]
            update_resource_log_params = {**log_params}
            update_user_params = {}
            for k in supported_update_keys:
                if account_user.get(k) is not None and account_user.get(
                    k
                ) != current_user.get(k):
                    update_resource_log_params[k] = dict(
                        old_value=current_user.get(k), new_value=account_user.get(k)
                    )
                    update_user_params[f"New{k}"] = account_user.get(k)
            if update_user_params:
                log_str = "Out of date resource found."
                if ctx.execute:
                    log.info(
                        f"{log_str} Updating resource...",
                        **update_resource_log_params,
                    )

                    async def update_user():
                        exceptions = []
                        try:
                            await boto_crud_call(
                                client.update_user,
                                UserName=user_name,
                                **{
                                    k: update_user_params.get(k)
                                    for k in update_user_params
                                },
                            )
                        except Exception as e:
                            exceptions.append(str(e))
                        return [
                            ProposedChange(
                                change_type=ProposedChangeType.UPDATE,
                                resource_id=user_name,
                                resource_type=self.resource_type,
                                exceptions_seen=exceptions,
                            )
                        ]

                    tasks.append(update_user())
                else:
                    log.info(log_str, **update_resource_log_params)
                    account_change_details.proposed_changes.append(
                        ProposedChange(
                            change_type=ProposedChangeType.UPDATE,
                            resource_id=user_name,
                            resource_type=self.resource_type,
                        )
                    )
        else:
            proposed_changes = [
                ProposedChange(
                    change_type=ProposedChangeType.CREATE,
                    resource_id=user_name,
                    resource_type=self.resource_type,
                )
            ]
            log_str = "New resource found in code."
            if not ctx.execute:
                # Exit now because apply functions won't work if resource doesn't exist
                log.debug(log_str, **log_params)
                account_change_details.extend_changes(proposed_changes)
                return account_change_details

            log_str = f"{log_str} Creating resource..."
            log.info(log_str, **log_params)
            if account_user.get("PermissionsBoundary"):
                account_user["PermissionsBoundary"] = account_user[
                    "PermissionsBoundary"
                ]["PolicyArn"]

            account_change_details.extend_changes(
                await plugin_apply_wrapper(
                    boto_crud_call(client.create_user, **account_user),
                    proposed_changes,
                )
            )

        tasks.extend(
            [
                apply_user_managed_policies(
                    user_name,
                    client,
                    managed_policies,
                    existing_managed_policies,
                    log_params,
                ),
                apply_user_inline_policies(
                    user_name,
                    client,
                    inline_policies,
                    existing_inline_policies,
                    log_params,
                ),
                apply_user_groups(
                    user_name,
                    client,
                    groups,
                    existing_groups,
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
