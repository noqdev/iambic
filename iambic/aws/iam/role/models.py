import asyncio
import json
from itertools import chain
from typing import Optional, Union

from pydantic import Field, constr

from iambic.aws.iam.models import Description, MaxSessionDuration, Path
from iambic.aws.iam.policy.models import (
    AssumeRolePolicyDocument,
    ManagedPolicyRef,
    PolicyDocument,
)
from iambic.aws.iam.role.utils import (  # get_role_managed_policies,
    apply_role_inline_policies,
    apply_role_managed_policies,
    apply_role_tags,
    delete_iam_role,
    get_role_inline_policies,
    update_assume_role_policy,
)
from iambic.aws.models import ARN_RE, AccessModel, AWSTemplate, ExpiryModel, Tag
from iambic.aws.utils import apply_to_account
from iambic.config.models import AWSAccount
from iambic.core.context import ctx
from iambic.core.logger import log
from iambic.core.models import AccountChangeDetails, ProposedChange, ProposedChangeType
from iambic.core.utils import aio_wrapper


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
        return "aws:iam:role_access"

    @property
    def resource_id(self):
        return


class PermissionBoundary(ExpiryModel, AccessModel):
    permissions_boundary_type: str
    permissions_boundary_arn: constr(regex=ARN_RE)

    @property
    def resource_type(self):
        return "aws:iam:permission_boundary"

    @property
    def resource_id(self):
        return self.permissions_boundary_arn


class RoleTemplate(AWSTemplate, AccessModel):
    template_type = "NOQ::AWS::IAM::ROLE"
    role_name: str = Field(
        description="Name of the role",
    )
    description: Optional[Union[str | list[Description]]] = Field(
        "",
        description="Description of the role",
    )
    owner: Optional[str] = None
    max_session_duration: Optional[Union[int | list[MaxSessionDuration]]] = 3600
    path: Optional[Union[str | list[Path]]] = "/"
    permissions_boundary: Optional[
        None | PermissionBoundary | list[PermissionBoundary]
    ] = None
    role_access: Optional[list[RoleAccess]] = Field(
        [],
        description="List of users and groups who can assume into the role",
    )
    assume_role_policy_document: Optional[
        None | AssumeRolePolicyDocument | list[AssumeRolePolicyDocument]
    ] = None
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

    def _apply_resource_dict(self, aws_account: AWSAccount = None) -> dict:
        response = super(RoleTemplate, self)._apply_resource_dict(aws_account)
        response.pop("RoleAccess", None)
        if "Tags" not in response:
            response["Tags"] = []

        # Add RoleAccess Tag to role tags
        role_access = [
            ra._apply_resource_dict(aws_account)
            for ra in self.role_access
            if apply_to_account(ra, aws_account)
        ]
        if role_access:
            value = []
            for role_access_dict in role_access:
                value.extend(role_access_dict.get("Users", []))
                value.extend(role_access_dict.get("Groups", []))
            response["Tags"].append(
                {"Key": aws_account.role_access_tag, "Value": ":".join(value)}
            )

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

    def _is_read_only(self, aws_account: AWSAccount):
        return (
            "aws-service-role" in self.path or aws_account.read_only or self.read_only
        )

    async def _apply_to_account(self, aws_account: AWSAccount) -> AccountChangeDetails:
        boto3_session = aws_account.get_boto3_session()
        client = boto3_session.client("iam")
        account_role = self.apply_resource_dict(aws_account)
        role_name = account_role["RoleName"]
        account_change_details = AccountChangeDetails(
            account=str(aws_account),
            resource_id=role_name,
            new_value=dict(**account_role),
            proposed_changes=[],
        )
        log_params = dict(
            resource_type=self.resource_type,
            resource_id=role_name,
            account=str(aws_account),
        )
        read_only = self._is_read_only(aws_account)

        try:
            current_role = (await aio_wrapper(client.get_role, RoleName=role_name))[
                "Role"
            ]
        except client.exceptions.NoSuchEntityException:
            current_role = {}

        deleted = self.get_attribute_val_for_account(aws_account, "deleted", False)
        if isinstance(deleted, list):
            deleted = deleted[0].deleted

        if deleted:
            if current_role:
                account_change_details.new_value = None
                account_change_details.current_value = current_role
                account_change_details.proposed_changes.append(
                    ProposedChange(
                        change_type=ProposedChangeType.DELETE,
                        resource_id=role_name,
                        resource_type=self.resource_type,
                    )
                )
                log_str = "Active resource found with deleted=false."
                if ctx.execute and not read_only:
                    log_str = f"{log_str} Deleting resource..."
                log.info(log_str, **log_params)

                if ctx.execute:
                    await delete_iam_role(role_name, client, log_params)

            return account_change_details

        role_exists = bool(current_role)
        # existing_inline_policy_map = {}
        # existing_managed_policies = []
        inline_policies = account_role.pop("InlinePolicies", [])
        managed_policies = account_role.pop("ManagedPolicies", [])
        tasks = []

        if role_exists:
            existing_inline_policy_map = await get_role_inline_policies(
                role_name, client
            )
            for k in existing_inline_policy_map.keys():
                existing_inline_policy_map[k]["PolicyName"] = k

            # role_inline_policies = list(existing_inline_policy_map.values())
            # managed_policies_resp = await get_role_managed_policies(role_name, client)
            # existing_managed_policies = [
            #     policy["PolicyArn"] for policy in managed_policies_resp
            # ]

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
                    log.info(
                        f"{log_str} Updating resource...", **update_resource_log_params
                    )
                    tasks.append(
                        aio_wrapper(
                            client.update_role,
                            RoleName=role_name,
                            **{k: account_role.get(k) for k in supported_update_keys},
                        )
                    )
                else:
                    log.info(log_str, **update_resource_log_params)
        else:
            account_change_details.proposed_changes.append(
                ProposedChange(
                    change_type=ProposedChangeType.CREATE,
                    resource_id=role_name,
                    resource_type=self.resource_type,
                )
            )
            log_str = "New resource found."
            if not ctx.execute:
                log.info(log_str, **log_params)
                # Exit now because apply functions won't work if resource doesn't exist
                return account_change_details

            log_str = f"{log_str} Creating resource..."
            log.info(log_str, **log_params)
            account_role["AssumeRolePolicyDocument"] = json.dumps(
                account_role["AssumeRolePolicyDocument"]
            )
            await aio_wrapper(client.create_role, **account_role)

        tasks.extend(
            [
                apply_role_managed_policies(
                    role_name,
                    client,
                    managed_policies,
                    role_exists,
                    log_params,
                ),
                apply_role_inline_policies(
                    role_name,
                    client,
                    inline_policies,
                    role_exists,
                    log_params,
                ),
            ]
        )

        changes_made = await asyncio.gather(*tasks)
        if any(changes_made):
            account_change_details.proposed_changes.extend(
                list(chain.from_iterable(changes_made))
            )

        if ctx.execute:
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
        return "aws:iam:role"

    @property
    def resource_id(self):
        return self.role_name
