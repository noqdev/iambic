import os
import tempfile

import pexpect

KEY_UP = "\x1b[A"
KEY_DOWN = "\x1b[B"


def test_setup_single_account() -> None:
    temp_templates_directory = tempfile.mkdtemp(
        prefix="iambic_test_temp_templates_directory"
    )
    log_file = f"{temp_templates_directory}/test_setup_single_aws_account.txt"
    print(f"ui test log file is in {log_file}")
    with open(log_file, "wb") as fout:
        spawn_env = dict(os.environ)
        spawn_env["PROMPT_TOOLKIT_NO_CPR"] = "1"
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
