# Intentionally hacky for demo
import json

import boto3

from noq_form.slack.notifications import send_iam_mutation_message


async def detect_changes(config) -> bool:
    session = boto3.Session()
    identity = session.client(
        "sts",
    ).get_caller_identity()
    identity_arn_with_session_name = (
        identity["Arn"].replace(":sts:", ":iam:").replace("assumed-role", "role")
    )
    identity_arn = "/".join(identity_arn_with_session_name.split("/")[0:2])
    queue_arn = config.sqs.get("queues", {}).get("iam_mutation", {}).get("arn", "")
    queue_name = queue_arn.split(":")[-1]
    sqs = boto3.client("sqs", region_name="us-east-1")
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
                        decoded_message = json.loads(message_body["Message"])["detail"]
                    else:
                        decoded_message = message_body["detail"]
                except Exception:
                    processed_messages.append(
                        {
                            "Id": message["MessageId"],
                            "ReceiptHandle": message["ReceiptHandle"],
                        }
                    )
                    continue
                role_name = decoded_message["requestParameters"]["roleName"]
                role_account_id = decoded_message.get(
                    "account", decoded_message.get("recipientAccountId")
                )
                role_arn = f"arn:aws:iam::{role_account_id}:role/{role_name}"
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
                    await send_iam_mutation_message(
                        config=config,
                        identity=role_arn,
                        actor=actor,
                        event_source=decoded_message["eventSource"],
                        event_name=decoded_message["eventName"],
                        session_name=session_name,
                        cloudtrail_event=decoded_message,
                    )
            except:
                continue
            
        sqs.delete_message_batch(QueueUrl=queue_url, Entries=processed_messages)
        messages = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10).get(
            "Messages", []
        )
    return True
