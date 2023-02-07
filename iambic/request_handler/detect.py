from __future__ import annotations

import asyncio
import json
from typing import Union

from iambic.aws.event_bridge.models import (
    GroupMessageDetails,
    ManagedPolicyMessageDetails,
    PermissionSetMessageDetails,
    RoleMessageDetails,
    UserMessageDetails,
)
from iambic.aws.iam.group.template_generation import generate_aws_group_templates
from iambic.aws.iam.policy.template_generation import (
    generate_aws_managed_policy_templates,
)
from iambic.aws.iam.role.template_generation import generate_aws_role_templates
from iambic.aws.iam.user.template_generation import generate_aws_user_templates
from iambic.aws.identity_center.permission_set.template_generation import (
    generate_aws_permission_set_templates,
)
from iambic.config.models import Config
from iambic.core.logger import log


async def detect_changes(  # noqa: C901
    config: Config, repo_dir: str
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
        tasks.append(generate_aws_role_templates([config], repo_dir, role_messages))
    if user_messages:
        tasks.append(generate_aws_user_templates([config], repo_dir, user_messages))
    if group_messages:
        tasks.append(generate_aws_group_templates([config], repo_dir, group_messages))
    if managed_policy_messages:
        tasks.append(
            generate_aws_managed_policy_templates(
                [config], repo_dir, managed_policy_messages
            )
        )
    if permission_set_messages:
        tasks.append(
            generate_aws_permission_set_templates(
                [config], repo_dir, permission_set_messages
            )
        )

    if tasks:
        await asyncio.gather(*tasks)
        return commit_message
