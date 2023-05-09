import os
import random
import tempfile
import time

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
        tui.sendline("")  # use default AWS
        tui.expect("What region should IAMbic use")
        tui.sendline("")  # use default us-east-1
        tui.expect("Which Account ID should we use to deploy the IAMbic hub role")
        tui.sendline("")  # use default account number
        tui.expect("Would you like to use this identity")
        tui.sendline("")  # use default
        tui.expect("What would you like to configure in AWS")
        tui.sendline(KEY_DOWN * 2)  # down twice to AWS Accounts
        tui.sendline("")  # use default account number
        tui.expect("Proceed")
        tui.sendline("")  # use default
        tui.expect("What is the name of the AWS Account")
        tui.sendline("hub_account")  # use default
        tui.expect("Grant IambicSpokeRole write access")
        tui.sendline("")  # use default
        tui.expect("Proceed")
        tui.sendline("")  # use default
        tui.expect("Role ARN")
        tui.sendline("")  # use default
        tui.expect("Add Tags")
        tui.sendline("\n")  # use default
        tui.expect("Proceed")
        tui.sendline("")  # use default
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
        tui.sendline("")  # use default AWS
        tui.expect("What region should IAMbic use")
        tui.sendline("")  # use default us-east-1
        tui.expect("Which Account ID should we use to deploy the IAMbic hub role")
        tui.sendline("")  # use default account number
        tui.expect("Would you like to use this identity")
        tui.sendline("")  # use default
        tui.expect("What would you like to configure in AWS")
        tui.sendline(KEY_DOWN)  # down once to AWS Organizations
        tui.expect("Is this the case")
        tui.sendline("")  # use default
        tui.expect("Proceed")
        tui.sendline("")  # use default
        tui.expect("AWS Organization ID")
        tui.sendline("")  # use default
        tui.expect("Grant IambicSpokeRole write access")
        tui.sendline("")  # use default
        tui.expect("Identity ARN")
        tui.sendline("")  # use default
        tui.expect("Role ARN")
        tui.sendline("")  # use default
        tui.expect("Proceed")
        tui.sendline("")  # use default
        tui.expect("Add Tags")
        tui.sendline("\n")  # use default
        tui.expect("Would you like to setup Identity Center")
        tui.sendline("")  # use default
        tui.expect("Keep these settings")
        tui.sendline("")  # use default
        tui.expect("Add the org accounts to the config and import the org")
        tui.sendline("")  # use default
        tui.expect("What would you like to configure", timeout=600)


def test_setup_org_account_with_stack_creation(iam_spoke_role) -> None:
    random_int = random.randint(0, 10000)
    unique_suffix = f"FuncTest{random_int}"
    iambic_hub_role_name = f"IambicHubRole{unique_suffix}"
    iambic_spoke_role_name = f"IambicSpokeRole{unique_suffix}"
    iambic_control_plane_region = "us-east-1"

    # stackset creation is slow. this test is known to be slow
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
            "iambic setup --more-options",
            timeout=5,
            env=spawn_env,
            logfile=fout,
            cwd=temp_templates_directory,
        )
        tui.expect("What would you like to configure")
        tui.sendline("")  # use default AWS
        tui.expect("What region should IAMbic use")
        tui.sendline("")  # use default us-east-1
        tui.expect("Which Account ID should we use to deploy the IAMbic hub role")
        tui.sendline("")  # use default account number
        tui.expect("Would you like to use this identity")
        tui.sendline("")  # use default
        tui.expect("What would you like to configure in AWS")
        tui.sendline(KEY_DOWN)  # down once to AWS Organizations
        tui.expect("Is this the case")
        tui.sendline("")  # use default
        tui.expect("Proceed")
        tui.sendline("")  # use default
        tui.expect("AWS Organization ID")
        tui.sendline("")  # use default
        tui.expect("Grant IambicSpokeRole write access")
        tui.sendline("")  # use default
        tui.expect("Identity ARN")
        tui.sendline("")  # use default
        tui.expect("Role ARN")
        tui.sendline("")  # use default
        tui.expect("Proceed")
        tui.sendline("")  # use default
        tui.expect("Iambic Hub Role Name")
        tui.sendline(iambic_hub_role_name)
        tui.expect("Iambic Spoke Role Name")
        tui.sendline(iambic_spoke_role_name)
        tui.expect("Add Tags")
        tui.sendline("team=engineering")  # use default
        tui.expect(
            "Would you like to setup Identity Center", timeout=600
        )  # stack set takes time
        tui.sendline("")  # use default
        tui.expect("Keep these settings")
        tui.sendline("")  # use default
        tui.expect("Add the org accounts to the config and import the org")
        tui.sendline("")  # use default
        tui.expect("What would you like to configure", timeout=600)

    # find out organization root
    org_client = boto3.client(
        "organizations",
        aws_access_key_id=iam_spoke_role["Credentials"]["AccessKeyId"],
        aws_secret_access_key=iam_spoke_role["Credentials"]["SecretAccessKey"],
        aws_session_token=iam_spoke_role["Credentials"]["SessionToken"],
        region_name=iambic_control_plane_region,
    )
    org_response = org_client.list_roots()
    org_root_id = org_response["Roots"][0]["Id"]

    # clean up cf resources
    cf_client = boto3.client(
        "cloudformation",
        aws_access_key_id=iam_spoke_role["Credentials"]["AccessKeyId"],
        aws_secret_access_key=iam_spoke_role["Credentials"]["SecretAccessKey"],
        aws_session_token=iam_spoke_role["Credentials"]["SessionToken"],
        region_name=iambic_control_plane_region,
    )
    _ = cf_client.delete_stack(
        StackName=iambic_hub_role_name,
    )
    _ = cf_client.delete_stack(
        StackName=iambic_spoke_role_name,
    )

    _ = cf_client.delete_stack_instances(
        StackSetName=iambic_spoke_role_name,
        DeploymentTargets={
            "OrganizationalUnitIds": [
                org_root_id,
            ],
            "AccountFilterType": "NONE",
        },
        Regions=[
            "us-east-1",
        ],
        OperationPreferences={
            "RegionConcurrencyType": "PARALLEL",
            "FailureTolerancePercentage": 100,
            "MaxConcurrentPercentage": 100,
        },
        RetainStacks=False,
    )
    # takes time to delete
    time.sleep(10)
    _ = cf_client.delete_stack_set(StackSetName=iambic_spoke_role_name)
