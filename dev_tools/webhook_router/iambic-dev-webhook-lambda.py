# This is a python file package to be deployed in Lambda Runtime.
# This serves as the simply routing layer for public internet
# reachable by GitHub Web Hooks. Try not to import package
# that is not already in lambda python runtime. Otherwise,
# we have to switch to container-base runtime. That impacts
# startup time and memory requirement.

from __future__ import annotations

import hashlib
import hmac
import json
import os

import boto3
from botocore.exceptions import ClientError

# Load from os.environ because this is executed by lambda
# Lambda environment is configured in terraform
DEV_WEBHOOK_SNS_ARN = os.environ["DEV_WEBHOOK_SNS_ARN"]
# Example format: "arn:aws:sns:us-east-2:444455556666:MyTopic"
topic_region = DEV_WEBHOOK_SNS_ARN.split(":")[3]
sns = boto3.client("sns", region_name=topic_region)

# Load from os.environ because this is executed by lambda
# Lambda environment is configured in terraform
GITHUB_APP_IAMBIC_DEV_SECRET_ARN = os.environ["GITHUB_APP_IAMBIC_DEV_SECRET_ARN"]
# Example format: arn:aws:secretsmanager:us-west-2:759357822767:secret:dev/github-app-noq-dev-HwkrMi


def get_webhook_secret(secret_arn):
    region_name = secret_arn.split(":")[3]

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(service_name="secretsmanager", region_name=region_name)

    try:
        get_secret_value_response = client.get_secret_value(SecretId=secret_arn)
    except ClientError as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        raise e

    # Decrypts secret using the associated KMS key.
    secret = get_secret_value_response["SecretString"]

    # secret is in yaml format, but i do not want to deal with
    # building or packaging yaml at this moment...
    # ["_global_"]["secrets"]["github_app"]["webhook_secret"]
    for line in secret.split("\n"):
        if "webhook_secret" in line:
            return line.strip().split(":")[1].strip()
    raise RuntimeError("Cannot parse webhook_secret")


# Ensure you read SECRET during function load time;
# This saves a lot of API request and cost. since
# Lambda function remains warm after 1 execution
GITHUB_APP_IAMBIC_DEV_WEBHOOK_SECRET = get_webhook_secret(
    GITHUB_APP_IAMBIC_DEV_SECRET_ARN
)


# Use to verify Github App Webhook Secret Using SHA256
def calculate_signature(webhook_secret: str, payload: str) -> str:
    secret_in_bytes = bytes(webhook_secret, "utf-8")
    digest = hmac.new(
        key=secret_in_bytes, msg=payload.encode("utf-8"), digestmod=hashlib.sha256
    )
    signature = digest.hexdigest()
    return signature


def verify_signature(sig: str, payload: str) -> None:
    good_sig = calculate_signature(GITHUB_APP_IAMBIC_DEV_WEBHOOK_SECRET, payload)
    if not hmac.compare_digest(good_sig, sig):
        raise RuntimeError("Invalid signature")


def lambda_handler(event, context):
    # TODO: shall we implement signature verification
    # here to cut down DDoS possibilities.
    headers = event["headers"]
    body = event["body"]

    # the format is in sha256=<sig>
    request_signature = headers["x-hub-signature-256"].split("=")[1]
    # because this handler is unauthenticated, always verify signature before taking action
    verify_signature(request_signature, body)

    # TODO: need a really fast implementation to translate
    # installation_id to topic_arn. it's difficult to use
    # message filter policy likely due to maximum size of
    # policy

    _ = sns.publish(
        TopicArn=DEV_WEBHOOK_SNS_ARN,
        Message=json.dumps(event),
        Subject="github",
        MessageStructure="string",
    )

    return {"statusCode": 200, "body": json.dumps("Stash to queue")}
