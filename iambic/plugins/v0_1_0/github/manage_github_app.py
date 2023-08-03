from __future__ import annotations

import json
import time

import jwt
import requests

from iambic.core.logger import log


def generate_jwt(github_secrets):
    pem_contents = github_secrets["pem"]
    app_id = github_secrets["id"]

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
        log.info("GitHub app webhook url is already up-to-date")
        return

    assert webhook_url.startswith("https://")
    payload = {
        "url": webhook_url,
    }
    log.info(f"We are updating your GitHub app's webhook URL to: {webhook_url}")
    r = requests.patch(control_plane_url, data=json.dumps(payload), headers=head)
    r.raise_for_status()


def verify_access(encoded_jwt):
    head = {
        "Authorization": f"Bearer {encoded_jwt}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    control_plane_url = "https://api.github.com/app/hook/config"

    r = requests.get(control_plane_url, headers=head)
    if r.status_code == 401:
        log.error(
            "Error code 401. Please verify your system time. If time is correct, you may need to remove ~/.iambic/.github_secrets.yaml and restart the process"
        )
        return False
    elif r.status_code == 404:
        log.error(
            "Error code 404. Your existing secrets are out-of-date. Please remove ~/.iambic/.github_secrets.yaml"
        )
        return False
    try:
        r.raise_for_status()
    except Exception as e:
        log.error(e)
        return False
    return True
