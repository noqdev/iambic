#!/usr/bin/env python3

# This script exists to handle GitHub App automation due to terraform provider
# has yet to support it. https://github.com/integrations/terraform-provider-github/issues/509

from __future__ import annotations

import json
import sys
import time

import jwt
import requests

# github_app_webhook_function_url = "https://c57kpjuheoly2ptr2mg2fwe5eq0zgifi.lambda-url.us-west-2.on.aws/"
# github_app_webhook_sns_topic_arn = "arn:aws:sns:us-west-2:615395543222:github-app-noq-webhook"


def generate_jwt(github_secrets):
    pem_contents = github_secrets["pem"]
    app_id = github_secrets["id"]

    # # Open PEM
    # signing_key = jwt.jwk_from_pem(pem_contents)

    payload = {
        # Issued at time
        "iat": int(time.time()),
        # JWT expiration time (10 minutes maximum)
        "exp": int(time.time()) + 600,
        # GitHub App's identifier
        "iss": app_id,
    }

    # Create JWT
    encoded_jwt = jwt.encode(payload, pem_contents, algorithm="RS256")
    return encoded_jwt


def update_webhook_url(webhook_url, encoded_jwt):
    head = {
        "Authorization": f"Bearer {encoded_jwt}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    control_plane_url = "https://api.github.com/app/hook/config"

    r = requests.get(control_plane_url, headers=head)
    r.raise_for_status()
    current_config = json.loads(r.content)

    current_webhook_url = current_config["url"]
    if current_webhook_url == webhook_url:
        print("GitHub app webhook url is already up-to-date")
        return

    print(f"GitHub App existing webhook url is {current_webhook_url}")
    assert webhook_url.startswith("https://")
    payload = {
        "url": webhook_url,
    }
    print(f"Update GitHub App url to {webhook_url}")
    r = requests.patch(control_plane_url, data=json.dumps(payload), headers=head)
    r.raise_for_status()


if __name__ == "__main__":
    aws_profile = sys.argv[1]
    private_key_arn = sys.argv[2]
    webhook_url = sys.argv[3]
    encoded_jwt = generate_jwt(aws_profile, private_key_arn)
    update_webhook_url(webhook_url, encoded_jwt)
