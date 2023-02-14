#!/usr/bin/env python3
import jwt
import time
import sys
import requests

from iambic.core.logger import log

import github
import json


GITHUB_APP_ID = "293178" # FIXME
GITHUB_APP_PEM_PATH = "/Users/stevenmoy/Downloads/steven-test-github-app.2023-02-13.private-key.pem" # FIXME
INSTANCE_OF_APP_INSTALLATION = "34179484" # FIXME

def get_app_bearer_token() -> str:
    #FIXME PEM PATH
    pem = GITHUB_APP_PEM_PATH
    #FIXME app_id
    app_id = GITHUB_APP_ID

    payload = {
        # Issued at time
        'iat': int(time.time()),
        # JWT expiration time (10 minutes maximum)
        'exp': int(time.time()) + 600,
        # GitHub App's identifier
        'iss': app_id
    }

    # Create JWT
    return jwt.encode(payload, get_app_private_key(), algorithm='RS256')

def get_app_private_key() -> str:
    # Open PEM
    with open(GITHUB_APP_PEM_PATH, 'rb') as pem_file:
        signing_key = pem_file.read()
    return signing_key


def list_installations() -> list:
    encoded_jwt = get_app_bearer_token()
    response = requests.get('https://api.github.com/app/installations',headers={'Accept': 'application/vnd.github.v3.text-match+json', "Authorization": f"Bearer {encoded_jwt}"})
    installations = json.loads(response.text)
    return installations

def get_installation_token() -> None:
    encoded_jwt = get_app_bearer_token()
    access_tokens_url = 'https://api.github.com/app/installations/34179484/access_tokens' # FIXME constant
    response = requests.post(access_tokens_url,headers={'Accept': 'application/vnd.github+json', "Authorization": f"Bearer {encoded_jwt}"})
    payload = json.loads(response.text)
    installation_token = payload["token"]
    return installation_token

    response = requests.get('https://api.github.com/installation/repositories',headers={'Accept': 'application/vnd.github+json', "Authorization": f"Bearer {installation_token}"})
    repos = json.loads(response.text)
    assert repos

    integration = github.GithubIntegration(
        GITHUB_APP_ID, get_app_private_key(), base_url="https://github.com/api/v3")

    install = integration.get_installation("noqdev", "iambic-templates-itest") # FIXME
    access = integration.get_access_token(install.id)
    return access.token


def post_pr_comment() -> None:
    # github_client = github.Github(
    #     app_auth=github.AppAuthentication(          # not supported until version 2.0 https://github.com/PyGithub/PyGithub/commits/5e27c10a3140c3b9bbf71a0b71c96e71e1e3496c/github/AppAuthentication.py
    #         app_id=GITHUB_APP_ID,
    #         private_key=get_app_private_key(),
    #         installation_id=INSTANCE_OF_APP_INSTALLATION,
    #         ),
    # ) 
    # repo_name is already in the format {repo_owner}/{repo_short_name}
    github_client = github.Github(login_or_token=get_installation_token())
    repo_name = "noqdev/iambic-templates-itest" # FIXME constants
    pull_number = 248 # FIXME constants
    # repository_url_token
    templates_repo = github_client.get_repo(repo_name)
    pull_request = templates_repo.get_pull(pull_number)
    pull_request_branch_name = pull_request.head.ref
    log_params = {"pull_request_branch_name": pull_request_branch_name}
    log.info("PR remote branch name", **log_params)
    body = "posting as github app"
    pull_request.create_issue_comment(body)

def generate_jwt_for_server_to_server_communication() -> str:
    #FIXME PEM PATH
    pem = "/Users/stevenmoy/Downloads/steven-test-github-app.2023-02-13.private-key.pem"
    #FIXME app_id
    app_id = "293178"

    # Open PEM
    with open(pem, 'rb') as pem_file:
        signing_key = pem_file.read()

    payload = {
        # Issued at time
        'iat': int(time.time()),
        # JWT expiration time (10 minutes maximum)
        'exp': int(time.time()) + 600,
        # GitHub App's identifier
        'iss': app_id
    }

    # Create JWT
    encoded_jwt = jwt.encode(payload, signing_key, algorithm='RS256')

    print(f"JWT:  ", encoded_jwt)



    github_app = github_client.get_app()
    response = requests.get('https://api.github.com/app/installations',headers={'Accept': 'application/vnd.github.v3.text-match+json', "Authorization": f"Bearer {encoded_jwt}"})
    installations = json.loads(response.text)
    response


def run_handler(event=None, context=None):
    """
    Default handler for AWS Lambda. It is split out from the actual
    handler so we can also run via IDE run configurations
    """
    print(event)



if __name__ == "__main__":
    post_pr_comment()