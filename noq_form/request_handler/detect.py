# Intentionally hacky for demo
import json

from noq_form.config.models import Config
from noq_form.slack.notifications import send_iam_mutation_message
from noq_form.core.logger import log


async def detect_changes(config: Config) -> bool:
    queue_arn = config.sqs.get("queues", {}).get("iam_mutation", {}).get("arn", "")
    if not queue_arn:
        log.info("No queue arn found. Returning")
        return False

    queue_name = queue_arn.split(":")[-1]
    session = config.get_boto_session_from_arn(queue_arn)
    identity = session.client("sts").get_caller_identity()
    identity_arn_with_session_name = (
        identity["Arn"].replace(":sts:", ":iam:").replace("assumed-role", "role")
    )
    identity_arn = "/".join(identity_arn_with_session_name.split("/")[0:2])
    sqs = session.client("sqs", region_name="us-east-1")
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
            except Exception:
                continue

        sqs.delete_message_batch(QueueUrl=queue_url, Entries=processed_messages)
        messages = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10).get(
            "Messages", []
        )
    return True
