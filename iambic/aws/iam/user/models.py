from __future__ import annotations

import asyncio
from itertools import chain
from typing import Optional, Union

import botocore
from pydantic import Field, constr

from iambic.aws.iam.models import Path
from iambic.aws.iam.policy.models import ManagedPolicyRef, PolicyDocument
from iambic.aws.iam.user.utils import (
    apply_user_groups,
    apply_user_inline_policies,
    apply_user_managed_policies,
    apply_user_tags,
    delete_iam_user,
    get_user,
)
from iambic.aws.models import (
    ARN_RE,
    AccessModel,
    AWSAccount,
    AWSTemplate,
    Description,
    Tag,
)
from iambic.aws.utils import boto_crud_call, remove_expired_resources
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

AWS_IAM_USER_TEMPLATE_TYPE = "NOQ::AWS::IAM::User"


class PermissionBoundary(ExpiryModel, AccessModel):
    policy_arn: constr(regex=ARN_RE)

    @property
    def resource_type(self):
        return "aws:iam:permission_boundary"

    @property
    def resource_id(self):
        return self.policy_arn


class Group(ExpiryModel, AccessModel):
    group_name: str

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
    description: Optional[Union[str, list[Description]]] = Field(
        "",
        description="Description of the user",
    )
    owner: Optional[str] = None
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


class UserTemplate(AWSTemplate, AccessModel):
    template_type = AWS_IAM_USER_TEMPLATE_TYPE
    properties: UserProperties = Field(
        description="Properties of the user",
    )

    def _apply_resource_dict(
        self, aws_account: AWSAccount = None, context: ExecutionContext = None
    ) -> dict:
        response = super(UserTemplate, self)._apply_resource_dict(aws_account, context)
        if "Tags" not in response:
            response["Tags"] = []

        if permissions_boundary := response.pop("PermissionsBoundary", []):
            if isinstance(permissions_boundary, list):
                permissions_boundary = permissions_boundary[0]
            response["PermissionsBoundary"] = permissions_boundary

        if isinstance(response.get("Description"), list):
            response["Description"] = response["Description"][0]["Description"]

        return response

    def _is_iambic_import_only(self, aws_account: AWSAccount):
        return (
            aws_account.iambic_managed == IambicManaged.IMPORT_ONLY
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
        account_user = self.apply_resource_dict(aws_account, context)

        user_name = account_user["UserName"]
        account_change_details = AccountChangeDetails(
            account=str(aws_account),
            resource_id=user_name,
            new_value=dict(**account_user),
            proposed_changes=[],
        )
        log_params = dict(
            resource_type=self.resource_type,
            resource_id=user_name,
            account=str(aws_account),
        )
        iambic_import_only = self._is_iambic_import_only(aws_account)
        current_user = await get_user(user_name, client)
        if current_user:
            account_change_details.current_value = {**current_user}  # Create a new dict

        deleted = self.get_attribute_val_for_account(aws_account, "deleted", False)
        if isinstance(deleted, list):
            deleted = deleted[0].deleted

        if deleted:
            if current_user:
                account_change_details.new_value = None
                account_change_details.proposed_changes.append(
                    ProposedChange(
                        change_type=ProposedChangeType.DELETE,
                        resource_id=user_name,
                        resource_type=self.resource_type,
                    )
                )
                log_str = "Active resource found with deleted=false."
                if context.execute and not iambic_import_only:
                    log_str = f"{log_str} Deleting resource..."
                log.info(log_str, **log_params)

                if context.execute:
                    await delete_iam_user(user_name, client, log_params)

            return account_change_details

        user_exists = bool(current_user)
        inline_policies = account_user.pop("InlinePolicies", [])
        managed_policies = account_user.pop("ManagedPolicies", [])
        groups = account_user.pop("Groups", [])
        existing_inline_policies = current_user.pop("InlinePolicies", [])
        existing_managed_policies = current_user.pop("ManagedPolicies", [])
        existing_groups = current_user.pop("Groups", [])
        tasks = []
        try:
            if user_exists:
                tasks.extend(
                    [
                        apply_user_tags(
                            user_name,
                            client,
                            account_user["Tags"],
                            current_user.get("Tags", []),
                            log_params,
                            context,
                        ),
                    ]
                )

                supported_update_keys = ["Description", "MaxSessionDuration"]
                update_resource_log_params = {**log_params}
                update_user_params = {}
                for k in supported_update_keys:
                    if account_user.get(k) is not None and account_user.get(
                        k
                    ) != current_user.get(k):
                        update_resource_log_params[k] = dict(
                            old_value=current_user.get(k), new_value=account_user.get(k)
                        )
                        update_user_params[k] = current_user.get(k)

                if update_user_params:
                    log_str = "Out of date resource found."
                    if context.execute:
                        log.info(
                            f"{log_str} Updating resource...",
                            **update_resource_log_params,
                        )
                        tasks.append(
                            boto_crud_call(
                                client.update_user,
                                UserName=user_name,
                                **{
                                    k: account_user.get(k)
                                    for k in supported_update_keys
                                },
                            )
                        )
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
                account_change_details.proposed_changes.append(
                    ProposedChange(
                        change_type=ProposedChangeType.CREATE,
                        resource_id=user_name,
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
                if account_user.get("PermissionsBoundary"):
                    account_user["PermissionsBoundary"] = account_user[
                        "PermissionsBoundary"
                    ]["PolicyArn"]

                await boto_crud_call(client.create_user, **account_user)
        except Exception as e:
            log.error("Unable to generate tasks for resource", error=e, **log_params)
            return account_change_details

        tasks.extend(
            [
                apply_user_managed_policies(
                    user_name,
                    client,
                    managed_policies,
                    existing_managed_policies,
                    log_params,
                    context,
                ),
                apply_user_inline_policies(
                    user_name,
                    client,
                    inline_policies,
                    existing_inline_policies,
                    log_params,
                    context,
                ),
                apply_user_groups(
                    user_name,
                    client,
                    groups,
                    existing_groups,
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

    @property
    def resource_id(self):
        return self.properties.user_name
