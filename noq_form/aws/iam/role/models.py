import asyncio
import json
from typing import List, Optional, Union

from noq_form.aws.iam.policy.models import (
    AssumeRolePolicyDocument,
    ManagedPolicy,
    PolicyDocument,
)
from noq_form.aws.iam.role.utils import (
    apply_role_inline_policies,
    apply_role_managed_policies,
    apply_role_tags,
    delete_iam_role,
    update_assume_role_policy,
)
from noq_form.config.models import AccountConfig
from noq_form.core.context import ctx
from noq_form.core.logger import log
from noq_form.core.models import AccessModel, ExpiryModel, NoqTemplate, Tag
from noq_form.core.utils import aio_wrapper, apply_to_account


class RoleAccess(ExpiryModel, AccessModel):
    users: List[str] = []
    groups: List[str] = []

    @property
    def resource_type(self):
        return "Role Access"

    @property
    def resource_name(self):
        return


class PermissionBoundary(ExpiryModel, AccessModel):
    permissions_boundary_type: str
    permissions_boundary_arn: str


class Path(AccessModel):
    file_path: str


class MaxSessionDuration(AccessModel):
    max_session_duration: int


class MultiAccountRoleTemplate(NoqTemplate, AccessModel):
    template_type = "NOQ::IAM::MultiAccountRole"
    role_name: str
    description: Optional[str] = None
    owner: Optional[str] = None
    max_session_duration: Optional[Union[int | List[MaxSessionDuration]]] = 3600
    path: Optional[Union[str | List[Path]]] = "/"
    permissions_boundary: Optional[
        None | PermissionBoundary | List[PermissionBoundary]
    ] = None
    role_access: Optional[List[RoleAccess]] = []
    assume_role_policy_document: Optional[
        None | AssumeRolePolicyDocument | List[AssumeRolePolicyDocument]
    ] = None
    tags: Optional[List[Tag]] = []
    managed_policies: Optional[List[ManagedPolicy]] = []
    inline_policies: Optional[List[PolicyDocument]] = []

    def _apply_resource_dict(self, account_config: AccountConfig = None) -> dict:
        response = super(MultiAccountRoleTemplate, self)._apply_resource_dict(
            account_config
        )
        response.pop("RoleAccess", None)

        # Add RoleAccess Tag to role tags
        role_access = [
            ra._apply_resource_dict()
            for ra in self.role_access
            if apply_to_account(ra, account_config)
        ]
        if role_access:
            value = []
            for role_access_dict in role_access:
                value.extend(role_access_dict.get("Users", []))
                value.extend(role_access_dict.get("Groups", []))
            response["Tags"].append(
                {"Key": account_config.role_access_tag, "Value": ":".join(value)}
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

        return response

    async def _apply_to_account(self, account_config: AccountConfig) -> bool:
        boto3_session = account_config.get_boto3_session()
        client = boto3_session.client("iam")
        account_role = self.apply_resource_dict(account_config)
        role_name = account_role["RoleName"]
        log_params = dict(
            resource_type=self.resource_type,
            resource_name=role_name,
            account=str(account_config),
        )
        changes_made = False

        try:
            current_role = (await aio_wrapper(client.get_role, RoleName=role_name))[
                "Role"
            ]
        except client.exceptions.NoSuchEntityException:
            current_role = {}

        if not self.get_attribute_val_for_account(account_config, "deleted"):
            if current_role:
                log_str = "Active resource found with deleted=false."
                if ctx.execute:
                    log_str = f"{log_str} Deleting resource..."
                log.info(log_str, **log_params)

                if ctx.execute:
                    await delete_iam_role(role_name, client, log_params)

                changes_made = True

            return changes_made

        role_exists = bool(current_role)
        inline_policies = account_role.pop("InlinePolicies", [])
        managed_policies = account_role.pop("ManagedPolicies", [])
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
                ]
            )

            supported_update_keys = ["Description", "MaxSessionDuration"]
            update_resource_log_params = {**log_params}
            update_role_params = {}
            for k in supported_update_keys:
                if account_role.get(k) != current_role.get(k):
                    update_resource_log_params[k] = dict(
                        old_value=current_role.get(k), new_value=account_role.get(k)
                    )
                    update_role_params[k] = current_role.get(k)

            if update_role_params:
                changes_made = True
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
            log_str = "New resource found."
            if not ctx.execute:
                log.info(log_str, **log_params)
                # Exit now because apply functions won't work if resource doesn't exist
                return True

            log_str = f"{log_str} Creating resource..."
            log.info(log_str, **log_params)
            account_role["AssumeRolePolicyDocument"] = json.dumps(
                account_role["AssumeRolePolicyDocument"]
            )
            await aio_wrapper(client.create_role, **account_role)
            changes_made = True

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

        changes_made = any(await asyncio.gather(*tasks)) or changes_made

        if ctx.execute:
            log.debug(
                "Successfully finished execution on account for resource",
                changes_made=changes_made,
                **log_params,
            )
        else:
            log.debug(
                "Successfully finished scanning for drift on account for resource",
                requires_changes=changes_made,
                **log_params,
            )

        return changes_made

    @property
    def resource_type(self):
        return "role"

    @property
    def resource_name(self):
        return self.role_name
