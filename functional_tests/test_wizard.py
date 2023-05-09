import os
import tempfile

import boto3
import pexpect
import pytest

KEY_UP = "\x1b[A"
KEY_DOWN = "\x1b[B"


@pytest.fixture
def iam_spoke_role():
    # assumption, we already have an IambicHubRole access
    # we will then assume into IambicFunctionalTestWizardRole
    # to simulate bootstrapping Iambic
    sts_client = boto3.client("sts")
    response = sts_client.get_caller_identity()
    iambic_spoke_role_arn = response["Arn"]
    iambic_spoke_role_arn = iambic_spoke_role_arn[0 : iambic_spoke_role_arn.rindex("/")]
    iambic_spoke_role_arn = iambic_spoke_role_arn.replace("assumed-role", "role")
    iambic_spoke_role_arn = iambic_spoke_role_arn.replace(
        "IambicHubRole", "IambicFunctionalTestWizardRole"
    )
    print(iambic_spoke_role_arn)

    response = sts_client.assume_role(
        RoleArn=iambic_spoke_role_arn, RoleSessionName="functional_test"
    )
    assert "Credentials" in response
    yield response


def test_setup_single_account(iam_spoke_role) -> None:
    temp_templates_directory = tempfile.mkdtemp(
        prefix="iambic_test_temp_templates_directory"
    )
    log_file = f"{temp_templates_directory}/test_setup_single_aws_account.txt"
    print(f"ui test log file is in {log_file}")
    spawn_env = dict(os.environ)
    spawn_env["PROMPT_TOOLKIT_NO_CPR"] = "1"
    spawn_env["AWS_ACCESS_KEY_ID"] = iam_spoke_role["Credentials"]["AccessKeyId"]
    spawn_env["AWS_SECRET_ACCESS_KEY"] = iam_spoke_role["Credentials"][
        "SecretAccessKey"
    ]
    spawn_env["AWS_SESSION_TOKEN"] = iam_spoke_role["Credentials"]["SessionToken"]
    with open(log_file, "wb") as fout:
        tui = pexpect.spawn(
            "iambic setup",
            timeout=5,
            env=spawn_env,
            logfile=fout,
            cwd=temp_templates_directory,
        )
        tui.expect("What would you like to configure")
        tui.sendline("\r")  # use default AWS
        tui.expect("What region should IAMbic use")
        tui.sendline("\r")  # use default us-east-1
        tui.expect("Which Account ID should we use to deploy the IAMbic hub role")
        tui.sendline("\r")  # use default account number
        tui.expect("Would you like to use this identity")
        tui.sendline("\r")  # use default Y
        tui.expect("What would you like to configure in AWS")
        tui.sendline(KEY_DOWN * 2)  # down twice to AWS Accounts
        tui.sendline("\r")  # use default account number
        tui.expect("Proceed")
        tui.sendline("Y")  # use default Y
        tui.expect("What is the name of the AWS Account")
        tui.sendline("hub_account\r")  # use default Y
        tui.expect("Grant IambicSpokeRole write access")
        tui.sendline("Y\r")  # use default Y
        tui.expect("Proceed")
        tui.sendline("\r")  # use default
        tui.expect("Role ARN")
        tui.sendline("\r")  # use default
        tui.expect("Add Tags")
        tui.sendline("\r\n")  # use default
        tui.expect("Proceed")
        tui.sendline("\r")  # use default
        tui.expect("What would you like to do", timeout=120)


def test_setup_org_account(iam_spoke_role) -> None:
    temp_templates_directory = tempfile.mkdtemp(
        prefix="iambic_test_temp_templates_directory"
    )
    log_file = f"{temp_templates_directory}/test_setup_org_account.txt"
    print(f"ui test log file is in {log_file}")
    spawn_env = dict(os.environ)
    spawn_env["PROMPT_TOOLKIT_NO_CPR"] = "1"
    spawn_env["AWS_ACCESS_KEY_ID"] = iam_spoke_role["Credentials"]["AccessKeyId"]
    spawn_env["AWS_SECRET_ACCESS_KEY"] = iam_spoke_role["Credentials"][
        "SecretAccessKey"
    ]
    spawn_env["AWS_SESSION_TOKEN"] = iam_spoke_role["Credentials"]["SessionToken"]
    with open(log_file, "wb") as fout:
        tui = pexpect.spawn(
            "iambic setup",
            timeout=5,
            env=spawn_env,
            logfile=fout,
            cwd=temp_templates_directory,
        )
        tui.expect("What would you like to configure")
        tui.sendline("\r")  # use default AWS
        tui.expect("What region should IAMbic use")
        tui.sendline("\r")  # use default us-east-1
        tui.expect("Which Account ID should we use to deploy the IAMbic hub role")
        tui.sendline("\r")  # use default account number
        tui.expect("Would you like to use this identity")
        tui.sendline("\r")  # use default Y
        tui.expect("What would you like to configure in AWS")
        tui.sendline(KEY_DOWN)  # down once to AWS Organizations
        tui.sendline("\r")  # use default account number
        tui.expect("Proceed")
        tui.sendline("Y")  # use default Y
        tui.expect("AWS Organization ID")
        tui.sendline("\r")  # use default
        tui.expect("Grant IambicSpokeRole write access")
        tui.sendline("Y\r")  # use default Y
        tui.expect("Identity ARN")
        tui.sendline("\r")  # use default
        tui.expect("Role ARN")
        tui.sendline("\r")  # use default
        tui.expect("Add Tags")
        tui.sendline("\r\n")  # use default
        tui.expect("Would you like to setup Identity Center")
        tui.sendline("\r")  # use default
        tui.expect("Keep these settings")
        tui.sendline("\r")  # use default
        tui.expect("Add the org accounts to the config and import the org")
        tui.sendline("\r")  # use default
        tui.expect("What would you like to configure", timeout=600)
