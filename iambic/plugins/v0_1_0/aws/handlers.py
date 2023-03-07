from __future__ import annotations

import asyncio
import base64
import json
from typing import TYPE_CHECKING, Union

import boto3
from iambic.config.dynamic_config import ExtendsConfig, ExtendsConfigKey
from iambic.core.context import ctx
from iambic.core.iambic_enum import IambicManaged
from iambic.core.logger import log
from iambic.core.models import BaseTemplate, TemplateChangeDetails
from iambic.core.parser import load_templates
from iambic.core.utils import gather_templates, yaml
from iambic.plugins.v0_1_0.aws.event_bridge.models import (
    GroupMessageDetails,
    ManagedPolicyMessageDetails,
    PermissionSetMessageDetails,
    RoleMessageDetails,
    UserMessageDetails,
)
from iambic.plugins.v0_1_0.aws.iam.group.template_generation import (
    generate_aws_group_templates,
)
from iambic.plugins.v0_1_0.aws.iam.policy.template_generation import (
    generate_aws_managed_policy_templates,
)
from iambic.plugins.v0_1_0.aws.iam.role.template_generation import (
    generate_aws_role_templates,
)
from iambic.plugins.v0_1_0.aws.iam.user.template_generation import (
    generate_aws_user_templates,
)
from iambic.plugins.v0_1_0.aws.identity_center.permission_set.models import (
    AWSIdentityCenterPermissionSetTemplate,
)
from iambic.plugins.v0_1_0.aws.identity_center.permission_set.template_generation import (
    generate_aws_permission_set_templates,
)
from iambic.plugins.v0_1_0.aws.identity_center.permission_set.utils import (
    generate_permission_set_map,
)
from iambic.plugins.v0_1_0.aws.models import AWSAccount

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig


async def load(config: AWSConfig, sparse: bool = False) -> AWSConfig:
    config_account_idx_map = {
        account.account_id: idx for idx, account in enumerate(config.accounts)
    }
    if sparse:
        return config
    if config.organizations:
        if any(account.hub_role_arn for account in config.accounts):
            log.warning(
                "You have a `hub_role_arn` defined on an `aws.account` specified in your IAMbic configuration that will be ignored. "
                "IAMbic will prefer the `hub_role_arn` specified under your AWS Organization. To remove this message, "
                "please remove the `hub_role_arn` specified in an `AWS Account`."
            )
        orgs_accounts = await asyncio.gather(
            *[org.get_accounts() for org in config.organizations]
        )
        for org_accounts in orgs_accounts:
            for account in org_accounts:
                if (
                    account_elem := config_account_idx_map.get(account.account_id)
                ) is not None:
                    config.accounts[
                        account_elem
                    ].hub_session_info = account.hub_session_info
                    config.accounts[
                        account_elem
                    ].identity_center_details = account.identity_center_details
                else:
                    log.warning(
                        "Account not found in config. Account will be ignored.",
                        account_id=account.account_id,
                        account_name=account.account_name,
                    )
    elif config.accounts:
        hub_account = [account for account in config.accounts if account.hub_role_arn]
        if len(hub_account) > 1:
            raise AttributeError("Only one AWS Account can specify the hub_role_arn")
        elif not hub_account:
            raise AttributeError("One of the AWS Accounts must define the hub_role_arn")
        else:
            hub_account = hub_account[0]
            await hub_account.set_hub_session_info()
            hub_session_info = hub_account.hub_session_info
            if not hub_session_info:
                raise Exception("Unable to assume into the hub_role_arn")
            for account in config.accounts:
                if account.account_id != hub_account.account_id:
                    account.hub_session_info = hub_session_info
    return config


async def apply(
    config: AWSConfig, templates: list[BaseTemplate]
) -> list[TemplateChangeDetails]:
    """
    The apply callable for the AWS IambicPlugin class.

    :param config: The config object.
    :param templates: The list of templates to apply.
    """
    if any(
        isinstance(template, AWSIdentityCenterPermissionSetTemplate)
        for template in templates
    ):
        await generate_permission_set_map(config.accounts, templates)

    template_changes: list[TemplateChangeDetails] = await asyncio.gather(
        *[template.apply(config, ctx) for template in templates]
    )

    return [
        template_change
        for template_change in template_changes
        if template_change.proposed_changes or template_change.exceptions_seen
    ]


async def import_aws_resources(
    config: AWSConfig, base_output_dir: str, messages: list = None
):
    await config.set_identity_center_details()

    await asyncio.gather(
        generate_aws_permission_set_templates(config, base_output_dir, messages),
        generate_aws_role_templates(config, base_output_dir, messages),
    )
    await generate_aws_user_templates(config, base_output_dir, messages)
    await generate_aws_group_templates(config, base_output_dir, messages)
    await generate_aws_managed_policy_templates(config, base_output_dir, messages)


async def detect_changes(  # noqa: C901
    config: AWSConfig, repo_dir: str
) -> Union[str, None]:
    if not config.sqs_cloudtrail_changes_queues:
        log.debug("No cloudtrail changes queue arn found. Returning")
        return

    role_messages = []
    user_messages = []
    group_messages = []
    managed_policy_messages = []
    permission_set_messages = []
    commit_message = "Out of band changes detected.\nSummary:\n"

    for queue_arn in config.sqs_cloudtrail_changes_queues:
        queue_name = queue_arn.split(":")[-1]
        region_name = queue_arn.split(":")[3]
        session = await config.get_boto_session_from_arn(queue_arn, region_name)
        identity = session.client("sts").get_caller_identity()
        identity_arn_with_session_name = (
            identity["Arn"].replace(":sts:", ":iam:").replace("assumed-role", "role")
        )
        # TODO: This only works for same account identities. We need to do similar to NoqMeter,
        # check all roles we have access to on all accounts, or store this in configuration.
        # Then exclude these from the list of roles to check.

        identity_arn = "/".join(identity_arn_with_session_name.split("/")[0:2])
        sqs = session.client("sqs", region_name=region_name)
        queue_url_res = sqs.get_queue_url(QueueName=queue_name)
        queue_url = queue_url_res.get("QueueUrl")
        messages = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10).get(
            "Messages", []
        )

        while messages:
            processed_messages = []
            for message in messages:
                try:
                    processed_messages.append(
                        {
                            "Id": message["MessageId"],
                            "ReceiptHandle": message["ReceiptHandle"],
                        }
                    )
                    message_body = json.loads(message["Body"])
                    try:
                        if "Message" in message_body:
                            decoded_message = json.loads(message_body["Message"])[
                                "detail"
                            ]
                        else:
                            decoded_message = message_body["detail"]
                    except Exception as err:
                        log.debug(
                            "Unable to process message", error=str(err), message=message
                        )
                        processed_messages.append(
                            {
                                "Id": message["MessageId"],
                                "ReceiptHandle": message["ReceiptHandle"],
                            }
                        )
                        continue
                    actor = (
                        decoded_message.get("userIdentity", {})
                        .get("sessionContext", {})
                        .get("sessionIssuer", {})
                        .get("arn", "")
                    )
                    session_name = (
                        decoded_message.get("userIdentity", {})
                        .get("principalId")
                        .split(":")[-1]
                    )
                    if actor != identity_arn:
                        account_id = decoded_message.get("recipientAccountId")
                        request_params = decoded_message["requestParameters"]
                        event = decoded_message["eventName"]
                        resource_id = None
                        resource_type = None
                        if role_name := request_params.get("roleName"):
                            resource_id = role_name
                            resource_type = "Role"
                            role_messages.append(
                                RoleMessageDetails(
                                    account_id=account_id,
                                    role_name=role_name,
                                    delete=bool(event == "DeleteRole"),
                                )
                            )
                        elif user_name := request_params.get("userName"):
                            resource_id = user_name
                            resource_type = "User"
                            user_messages.append(
                                UserMessageDetails(
                                    account_id=account_id,
                                    role_name=user_name,
                                    delete=bool(event == "DeleteUser"),
                                )
                            )
                        elif group_name := request_params.get("groupName"):
                            resource_id = group_name
                            resource_type = "Group"
                            group_messages.append(
                                GroupMessageDetails(
                                    account_id=account_id,
                                    group_name=group_name,
                                    delete=bool(event == "DeleteGroup"),
                                )
                            )
                        elif policy_arn := request_params.get("policyArn"):
                            split_policy = policy_arn.split("/")
                            policy_name = split_policy[-1]
                            policy_path = (
                                "/"
                                if len(split_policy) == 2
                                else f"/{'/'.join(split_policy[1:-1])}/"
                            )
                            resource_id = policy_name
                            resource_type = "ManagedPolicy"
                            managed_policy_messages.append(
                                ManagedPolicyMessageDetails(
                                    account_id=account_id,
                                    policy_name=policy_name,
                                    policy_path=policy_path,
                                    delete=bool(
                                        decoded_message["eventName"] == "DeletePolicy"
                                    ),
                                )
                            )
                        elif permission_set_arn := request_params.get(
                            "permissionSetArn"
                        ):
                            resource_id = permission_set_arn
                            resource_type = "PermissionSet"
                            permission_set_messages.append(
                                PermissionSetMessageDetails(
                                    account_id=account_id,
                                    instance_arn=request_params.get("instanceArn"),
                                    permission_set_arn=permission_set_arn,
                                )
                            )

                        if resource_id:
                            commit_message = (
                                f"{commit_message}User {session_name} performed action {event} "
                                f"on {resource_type}({resource_id}) on account {account_id}.\n"
                            )
                except Exception as err:
                    log.debug(
                        "Unable to process message", error=str(err), message=message
                    )
                    continue

            sqs.delete_message_batch(QueueUrl=queue_url, Entries=processed_messages)
            messages = sqs.receive_message(
                QueueUrl=queue_url, MaxNumberOfMessages=10
            ).get("Messages", [])

    tasks = []
    if role_messages:
        tasks.append(generate_aws_role_templates(config, repo_dir, role_messages))
    if user_messages:
        tasks.append(generate_aws_user_templates(config, repo_dir, user_messages))
    if group_messages:
        tasks.append(generate_aws_group_templates(config, repo_dir, group_messages))
    if managed_policy_messages:
        tasks.append(
            generate_aws_managed_policy_templates(
                config, repo_dir, managed_policy_messages
            )
        )
    if permission_set_messages:
        tasks.append(
            generate_aws_permission_set_templates(
                config, repo_dir, permission_set_messages
            )
        )

    if tasks:
        await asyncio.gather(*tasks)
        return commit_message


async def decode_aws_secret(config: AWSConfig, extend: ExtendsConfig) -> dict:
    if extend.key.value != ExtendsConfigKey.AWS_SECRETS_MANAGER.value:
        return {}

    assume_role_arn = extend.assume_role_arn
    secret_arn = extend.value
    region_name = secret_arn.split(":")[3]
    secret_account_id = secret_arn.split(":")[4]
    aws_account_map = {account.account_id: account for account in config.accounts}
    session = None

    if aws_account := aws_account_map.get(secret_account_id):
        if assume_role_arn == aws_account.spoke_role_arn:
            session = await aws_account.get_boto3_session(region_name=region_name)

    if not session and (config.accounts or config.organizations):
        if config.organizations:
            boto3_session = await config.organizations[0].get_boto3_session()
        else:
            hub_account = [
                account for account in config.accounts if account.hub_role_arn
            ][0]
            boto3_session = await hub_account.get_boto3_session()

        secret_account = AWSAccount(
            account_id=secret_account_id,
            account_name="Secret_Account",
            spoke_role_arn=assume_role_arn,
            hub_session_info=dict(boto3_session=boto3_session),
            boto3_session_map={},
        )
        session = await secret_account.get_boto3_session(region_name=region_name)
    elif not session:
        session = boto3.Session(region_name=region_name)

    try:
        client = session.client(service_name="secretsmanager")
        get_secret_value_response = client.get_secret_value(SecretId=secret_arn)
    except Exception:
        log.exception(
            "Unable to retrieve the AWS secret using the provided assume_role_arn",
            assume_role_arn=assume_role_arn,
            secret_arn=extend.value,
        )
        raise

    if "SecretString" in get_secret_value_response:
        return_val = get_secret_value_response["SecretString"]
    else:
        return_val = base64.b64decode(get_secret_value_response["SecretBinary"])

    return yaml.load(return_val)


async def discover_new_aws_accounts(
    config: AWSConfig,
    config_account_idx_map: dict[str, int],
    orgs_accounts: list[list[AWSAccount]],
    repo_dir: str,
) -> bool:
    run_apply = False
    run_import = False
    for org_accounts in orgs_accounts:
        for account in org_accounts:
            if config_account_idx_map.get(account.account_id) is None:
                config.accounts.append(account)
                log.warning(
                    "New AWS account discovered. Adding account to config.",
                    account_id=account.account_id,
                    account_name=account.account_name,
                )
                if account.iambic_managed not in [
                    IambicManaged.DISABLED,
                    IambicManaged.IMPORT_ONLY,
                ]:
                    run_apply = True

                if account.iambic_managed != IambicManaged.DISABLED:
                    run_import = True

    if run_apply:
        log.warning(
            "Applying templates to provision identities to the discovered account(s).",
        )
        templates = await gather_templates(repo_dir, "AWS.*")
        await apply(config, load_templates(templates))

    return run_import


async def discover_aws_account_attribute_changes(
    config: AWSConfig,
    config_account_idx_map: dict[str, int],
    orgs_accounts: list[list[AWSAccount]],
) -> bool:
    run_import = False
    for org_accounts in orgs_accounts:
        for account in org_accounts:
            if (
                account_elem := config_account_idx_map.get(account.account_id)
            ) is not None:
                config_account = config.accounts[account_elem]
                config_account_var_map = {
                    var["key"]: {"elem": idx, "value": var["value"]}
                    for idx, var in enumerate(config_account.variables)
                }

                if config_account.account_name != account.account_name:
                    log.warning(
                        "Updated AWS account name discovered. Updating account in config.",
                        account_id=account.account_id,
                        account_name=account.account_name,
                    )
                    config.accounts[account_elem].account_name = account.account_name
                    if account.iambic_managed != IambicManaged.DISABLED:
                        run_import = True

                for org_account_var in account.variables:
                    if config_account_var := config_account_var_map.get(
                        org_account_var.key
                    ):
                        if config_account_var["value"] != org_account_var.value:
                            log.warning(
                                "Mismatched variable on AWS account. Updating in config.",
                                account_id=account.account_id,
                                account_name=account.account_name,
                                variable_key=org_account_var.key,
                                discovered_value=org_account_var.value,
                                config_value=config_account_var["value"],
                            )
                            config.accounts[account_elem].variables[
                                config_account_var["elem"]
                            ].value = org_account_var.value
                            if account.iambic_managed != IambicManaged.DISABLED:
                                run_import = True

    return run_import


async def aws_account_update_and_discovery(config: AWSConfig, repo_dir: str):
    """
    Update and discover AWS accounts.

    This function updates the list of AWS accounts in the `config` object by retrieving the list of accounts
    from the AWS Organizations and checking for any new or updated accounts. If any new or updated accounts
    are found, the function imports the AWS resources and regenerates the AWS templates.

    Args:
    - config (AWSConfig): The AWS configuration object.
    - repo_dir (str): The directory path for the repository.

    Returns:
    - None
    """
    if not config.organizations:
        return

    ctx.eval_only = False
    config_account_idx_map = {
        account.account_id: idx for idx, account in enumerate(config.accounts)
    }

    orgs_accounts = await asyncio.gather(
        *[org.get_accounts() for org in config.organizations]
    )
    import_new_account = await discover_new_aws_accounts(
        config, config_account_idx_map, orgs_accounts, repo_dir
    )
    import_updated_account = await discover_aws_account_attribute_changes(
        config, config_account_idx_map, orgs_accounts
    )
    if import_new_account or import_updated_account:
        log.warning(
            "Running import to regenerate AWS templates.",
        )
        # Replace this with the aws one
        await import_aws_resources(config, repo_dir)
