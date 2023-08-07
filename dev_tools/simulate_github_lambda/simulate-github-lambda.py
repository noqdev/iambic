from __future__ import annotations

import json
import os
from functools import cache
from unittest.mock import patch

import boto3
import yaml

from iambic.core.logger import log
from iambic.plugins.v0_1_0.github.github_app import run_handler

DEV_REGION = os.environ.get("DEV_REGION", "us-west-2")
DEV_EMAIL_DOMAIN_SUFFIX = os.environ.get("DEV_EMAIL_DOMAIN_SUFFIX", "@example.com")
DEV_ACCOUNT_ID = os.environ.get("DEV_ACCOUNT_ID", "")
DEV_WEBHOOK_SNS_ARN = os.environ.get("DEV_WEBHOOK_SNS_ARN", "")

# You cannot proceed without these value. Check your environment setup.
assert DEV_ACCOUNT_ID
assert DEV_WEBHOOK_SNS_ARN


def get_developer_queue_name() -> str:
    sts_client = boto3.client("sts", region_name=DEV_REGION)
    response = sts_client.get_caller_identity()
    arn = response["Arn"]
    session_name = arn.split("/")[-1]
    assert session_name.endswith(DEV_EMAIL_DOMAIN_SUFFIX)
    developer_name = session_name.split(DEV_EMAIL_DOMAIN_SUFFIX)[0]
    developer_name = developer_name.replace(".", "__dot__")
    return f"iambic-dev-github-webhook-{developer_name}"


def get_developer_queue_arn() -> str:
    queue_name = get_developer_queue_name()
    developer_queue_arn = f"arn:aws:sqs:{DEV_REGION}:{DEV_ACCOUNT_ID}:{queue_name}"
    return developer_queue_arn


def allow_sns_to_write_to_sqs(topic_arn, queue_arn):
    policy_document = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "MyPolicy",
                "Effect": "Allow",
                "Principal": {"AWS": "*"},
                "Action": "SQS:SendMessage",
                "Resource": queue_arn,
                "Condition": {"ArnEquals": {"aws:SourceArn": topic_arn}},
            }
        ],
    }
    return json.dumps(policy_document)


def bootstrap_local_dev_sqs():
    # ideompotent bootstrap per developer queue name
    sqs_client = boto3.client("sqs", region_name=DEV_REGION)
    developer_queue_name = get_developer_queue_name()
    queue_arn = get_developer_queue_arn()
    try:
        _ = sqs_client.get_queue_url(
            QueueName=developer_queue_name,
        )
    except sqs_client.exceptions.QueueDoesNotExist:
        _ = sqs_client.create_queue(
            QueueName=developer_queue_name,
        )
    policy_json = allow_sns_to_write_to_sqs(DEV_WEBHOOK_SNS_ARN, queue_arn)

    response = sqs_client.get_queue_url(
        QueueName=developer_queue_name,
    )
    response = sqs_client.set_queue_attributes(
        QueueUrl=response["QueueUrl"], Attributes={"Policy": policy_json}
    )
    assert response
    # use a different block to ensure subscription to sns topic
    # SNS side seems to make sure it's idemopotent
    sns_client = boto3.client("sns", region_name=DEV_REGION)
    response = sns_client.subscribe(
        TopicArn=DEV_WEBHOOK_SNS_ARN,
        Protocol="sqs",
        Endpoint=queue_arn,
        ReturnSubscriptionArn=True,
    )
    assert response


def consume_message(message):
    try:
        # do your work
        webhook_request = json.loads(json.loads(message.body)["Message"])
        run_handler(webhook_request, None)

        return message.receipt_handle
    except Exception as e:
        log.error(e)
        return None


def receive_messages(queue, max_number, wait_time):
    """
    Receive a batch of messages in a single request from an SQS queue.

    :param queue: The queue from which to receive messages.
    :param max_number: The maximum number of messages to receive. The actual number
                       of messages received might be less.
    :param wait_time: The maximum time to wait (in seconds) before returning. When
                      this number is greater than zero, long polling is used. This
                      can result in reduced costs and fewer false empty responses.
    :return: The list of Message objects received. These each contain the body
             of the message and metadata and custom attributes.
    """
    try:
        messages = queue.receive_messages(
            MessageAttributeNames=["All"],
            MaxNumberOfMessages=max_number,
            WaitTimeSeconds=wait_time,
        )
        processed_messages = []
        for msg in messages:
            receipt = consume_message(msg)
            if receipt:
                processed_messages.append(receipt)

        # delete the successfully consumed messages
        delete_messages(queue, processed_messages)

    except Exception as error:
        log.error("Couldn't receive messages from queue: %s", queue)
        raise error
    else:
        return messages


def delete_messages(queue, list_of_receipts):
    """
    Delete a batch of messages from a queue in a single request.

    :param queue: The queue from which to delete the messages.
    :param messages: The list of messages to delete.
    :return: The response from SQS that contains the list of successful and failed
             message deletions.
    """
    try:
        entries = [
            {"Id": str(ind), "ReceiptHandle": receipt}
            for ind, receipt in enumerate(list_of_receipts)
        ]
        if not entries:
            return None
        response = queue.delete_messages(Entries=entries)
        if "Successful" in response:
            for msg_meta in response["Successful"]:
                log.info("Deleted %s", list_of_receipts[int(msg_meta["Id"])])
        if "Failed" in response:
            for msg_meta in response["Failed"]:
                log.warning(
                    "Could not delete %s", list_of_receipts[int(msg_meta["Id"])]
                )
    except Exception:
        log.error("Couldn't delete messages from queue %s", queue)
    else:
        return response


@cache
def _get_app_secrets_as_lambda_context_current() -> dict:
    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(service_name="secretsmanager", region_name=DEV_REGION)

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId="iambic-dev/github-secrets"
        )
    except Exception as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        raise e

    # Decrypts secret using the associated KMS key.
    return yaml.safe_load(get_secret_value_response["SecretString"])


if __name__ == "__main__":
    bootstrap_local_dev_sqs()
    sqs_client = boto3.client("sqs", region_name=DEV_REGION)
    sqs = boto3.resource("sqs", region_name=DEV_REGION)
    queue_url = sqs_client.get_queue_url(QueueName=get_developer_queue_name())[
        "QueueUrl"
    ]
    queue = sqs.Queue(queue_url)

    # to simulate lambda, we are pretending to be a lambda function
    os.environ["AWS_LAMBDA_FUNCTION_NAME"] = "simulate-github-lambda.py"

    with patch(
        "iambic.plugins.v0_1_0.github.github_app._get_app_secrets_as_lambda_context_current",
        new=_get_app_secrets_as_lambda_context_current,
    ):
        while True:
            receive_messages(queue, 10, 20)
