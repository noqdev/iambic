from __future__ import annotations

import json
import subprocess

import pytest

# The below profile only works if you have your own cloud resources and matching aws profile
TERRAFORM_AWS_PROFILE = (
    "iambic_test_org_spoke_account_1/iambic_test_org_spoke_account_1_admin"
)


@pytest.fixture
def generate_templates_fixture():
    # to override the conftest version to speed up testing
    pass


@pytest.fixture
def deploy_lambda():
    # subprocess.run("make -f Makefile.itest auth_to_ecr", shell=True, check=True)
    # subprocess.run(
    #     "make -f Makefile.itest build_docker_itest", shell=True, check=True
    # )
    # subprocess.run(
    #     "make -f Makefile.itest upload_docker_itest", shell=True, check=True
    # )

    # terraform workspace new branch-123
    # terraform apply
    # terraform destroy
    # terraform workspace select default
    # terraform workspace delete branch-123

    branch = "branch-456"

    setup_string = f"cd deployment/github_app_test && terraform workspace new {branch} && terraform apply -var aws_profile={TERRAFORM_AWS_PROFILE} -auto-approve"
    # print(setup_string)
    subprocess.run(setup_string, shell=True, check=True)

    show_output_string = f"cd deployment/github_app_test && terraform workspace select {branch} && terraform output -json"
    terraform_output_string = subprocess.check_output(show_output_string, shell=True)
    terraform_output = json.loads(terraform_output_string)

    yield terraform_output["function_url"]["value"]

    destroy_string = f"cd deployment/github_app_test && terraform workspace select {branch} && terraform destroy -var aws_profile={TERRAFORM_AWS_PROFILE} -auto-approve"
    subprocess.run(destroy_string, shell=True, check=True)

    destroy_workspace_string = f"cd deployment/github_app_test && terraform workspace select default && terraform workspace delete {branch}"
    subprocess.run(destroy_workspace_string, shell=True, check=True)

    return 1


def test_bootstrap(deploy_lambda):
    print(deploy_lambda)
    assert deploy_lambda is not None
