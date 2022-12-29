from __future__ import annotations

import asyncio
import contextlib
import os

import boto3
import questionary
from botocore.exceptions import ClientError

from iambic.aws.models import (
    AssumeRoleConfiguration,
    AWSAccount,
    AWSOrgAccountRule,
    AWSOrganization,
    BaseAWSOrgRule,
)
from iambic.aws.utils import get_account_id_from_arn, get_current_role_arn
from iambic.config.models import Config
from iambic.core.context import ctx
from iambic.core.logger import log
from iambic.core.parser import load_templates

IAMBIC_SPOKE_ROLE_TEMPLATE_FP = os.path.join(
    os.path.dirname(__file__), "../aws/templates/iambicspokerole.yaml"
)
SPOKE_ROLE_TEMPLATE = load_templates([IAMBIC_SPOKE_ROLE_TEMPLATE_FP])[0]


class ConfigurationWizard:
    def __init__(self, config_path: str):
        # TODO: Handle the case where the config file exists but is not valid
        self.config_path = config_path
        session = boto3.Session()
        self.autodetected_org_settings = {}
        self.current_account_name = None
        self.current_role_arn = None
        self.current_account_id = None
        self.default_region = session.region_name or "us-east-1"

        with contextlib.suppress(ClientError):
            self.current_role_arn = asyncio.run(get_current_role_arn())
            self.current_account_id = get_account_id_from_arn(self.current_role_arn)

        if not self.current_role_arn:
            log.error(
                "Unable to get current role ARN. If you'd like to bootstrap AWS "
                " accounts, please configure AWS credentials and re-run this command."
            )
        self.config: Config = Config.construct()
        if os.path.exists(config_path) and os.path.getsize(config_path) != 0:
            log.info("Found existing configuration file", config_path=config_path)
            with contextlib.suppress(FileNotFoundError):
                # Try to load a configuration
                self.config = Config.load(config_path)
        with contextlib.suppress(ClientError):
            self.autodetected_org_settings = session.client(
                "organizations"
            ).describe_organization()["Organization"]

        with contextlib.suppress(ClientError):
            self.current_account_name = (
                boto3.client("organizations")
                .describe_account(AccountId=self.current_account_id)
                .get("Account")
                .get("Name")
            )

        if self.current_account_name is None:
            with contextlib.suppress(ClientError):
                account_aliases = boto3.client("iam").list_account_aliases()[
                    "AccountAliases"
                ]
                if len(account_aliases) > 0:
                    self.current_account_name = account_aliases[0]
        log.debug("Starting configuration wizard", config_path=config_path)

    def bootstrap_accounts(self, accounts: list[AWSAccount]):

        # bootstraps AWS IAM roles and policies for an organization
        # async def _apply_to_account(  # noqa: C901
        #     self, aws_account: AWSAccount, context: ExecutionContext
        # )

        # Get current role - Assume this is the hub role
        # Or advise they create a hub role and we can assume that role
        # Successfully assume org role
        # Confirm with user
        # Create Spoke Role
        pass

    def configuration_wizard_aws_accounts(self):
        account_id = questionary.text(
            "What is the AWS Account ID? Usually this looks like `12345689012`",
            default=self.current_account_id,
        ).ask()

        account_name = questionary.text(
            "What is the name of the AWS Account?", default=self.curent_account_name
        ).ask()

        aws_profile = questionary.text(
            "(Optional) Provide an AWS profile name (Configured in ~/.aws/config) that Iambic "
            "should use when we access the AWS Organization. Note: "
            "this profile will be used before assuming any subsequent roles. "
            "(If you are using a role with access to the Organization and don't use "
            "a profile, you can leave this blank)",
            default=os.environ.get("AWS_PROFILE"),
        ).ask()
        if not aws_profile:
            aws_profile = None
        assume_role_arns = []
        assume_role_arn = questionary.text(
            "(Optional) Provide a role ARN to assume when accessing the AWS Organization"
            " from the current role. (If you are using a role with access to the Organization, "
            "you can leave this blank)"
        ).ask()

        if assume_role_arn:
            assume_role_arns = [AssumeRoleConfiguration(arn=assume_role_arn)]

        action = questionary.select(
            "Keep these settings? ",
            choices=["Yes", "No"],
        ).ask()

        if action == "No":
            return

        account = AWSAccount(
            account_id=account_id,
            account_name=account_name,
            aws_profile=aws_profile,
            assume_role_arns=assume_role_arns,
        )
        self.config.aws.accounts.append(account)

        action = questionary.select(
            "Bootstrap an Iambic Spoke Role on this accoun?",
            choices=["Yes", "No"],
        ).ask()

        if action == "No":
            return
        asyncio.run(SPOKE_ROLE_TEMPLATE._apply_to_account(account, ctx))

    def configuration_wizard_aws_organizations_edit(self):
        choices = ["Go back"]
        choices.extend(org.org_id for org in self.config.aws.organizations)
        while True:
            action = questionary.select(
                "Which AWS Organization would you like to edit?",
                choices=choices,
            ).ask()
            if action == "Go back":
                return
            org_to_edit = next(
                (org for org in self.config.aws.organizations if org.org_id == action),
                None,
            )
            if not org_to_edit:
                log.debug("Could not find AWS Organization to edit", org_id=action)
                return

    def configuration_wizard_aws_organizations_add(self):
        org_id = questionary.text(
            "What is the AWS Organization ID? Usually this looks like `o-123456`",
            default=self.autodetected_org_settings.get("Id"),
        ).ask()
        org_name = questionary.text(
            "What is the name of the AWS Organization?",
            default=self.current_account_name,
        ).ask()
        org_region = questionary.text(
            "What region is the AWS Organization in? (Such as `us-east-1`)",
            default=self.default_region,
        ).ask()

        aws_profile = questionary.text(
            "(Optional) Provide an AWS profile name (Configured in ~/.aws/config) that Iambic "
            "should use when we access the AWS Organization. Note: "
            "this profile will be used before assuming any subsequent roles. "
            "(If you are using a role with access to the Organization and don't use "
            "a profile, you can leave this blank)",
            default=os.environ.get("AWS_PROFILE"),
        ).ask()
        if not aws_profile:
            aws_profile = None
        assume_role_arns = []
        assume_role_arn = questionary.text(
            "(Optional) Provide a role ARN to assume when accessing the AWS Organization"
            " from the current role. (If you are using a role with access to the Organization, "
            "you can leave this blank)"
        ).ask()

        default_rule = BaseAWSOrgRule(enabled=True, read_only=False)
        if assume_role_arn:
            assume_role_arns = [AssumeRoleConfiguration(arn=assume_role_arn)]

        account_rules = [AWSOrgAccountRule(included_accounts=["*"])]
        action = questionary.select(
            "Keep these settings? ",
            choices=["Yes", "No"],
        ).ask()

        if action == "No":
            return

        aws_org = AWSOrganization(
            org_id=org_id,
            org_name=org_name,
            region=org_region,
            aws_profile=aws_profile,
            assume_role_arns=assume_role_arns,
            default_rule=default_rule,
            account_rules=account_rules,
        )

        log.debug("Attempting to get a session on the AWS org", org_id=org_id)
        try:
            session = asyncio.run(aws_org.get_boto3_session())
        except ClientError as e:
            log.error("Unable to get a session on the AWS org", org_id=org_id, error=e)
            session = None

        self.config.aws.organizations.append(aws_org)
        self.config.write(self.config_path)
        if session:
            org_role_arn = asyncio.run(get_current_role_arn(session))
            org_account_id = get_account_id_from_arn(org_role_arn)
            action = questionary.select(
                "Bootstrap an Iambic Spoke Role on this accoun?",
                choices=["Yes", "No"],
            ).ask()

            if action == "No":
                return

            account = AWSAccount(
                account_id=org_account_id,
                org_id=org_id,
                account_name=org_name,
                aws_profile=aws_profile,
                assume_role_arns=assume_role_arns,
            )

            asyncio.run(SPOKE_ROLE_TEMPLATE._apply_to_account(account, ctx))

    def generate_secrets_policy(self):
        # Generates a policy that allows access to secrets
        pass

    def configuration_wizard_aws_organizations_bootstrap():
        pass

    def configuration_wizard_aws_organizations(self):
        # Print existing AWS organizations
        while True:
            action = questionary.select(
                "How would you like to configure AWS Organizations? ",
                choices=[
                    "Go back",
                    "Add Organization",
                    "Edit Organization",
                    "Remove Organization",
                ],
            ).ask()
            if action == "Go back":
                return
            elif action == "Add Organization":
                self.configuration_wizard_aws_organizations_add()
            elif action == "Edit Organization":
                self.configuration_wizard_aws_organizations_edit()
            elif action == "Remove Organization":
                self.configuration_wizard_aws_organizations_remove()
            elif action == "Boostrap Organization":
                self.configuration_wizard_aws_organizations_bootstrap()

    def configuration_wizard_aws(self):
        while True:
            action = questionary.select(
                "What would you like to configure in AWS? "
                "We recommend configuring Iambic with AWS Organizations, "
                "but you may also manually configure accounts.",
                choices=["Go back", "AWS Organizations", "AWS Accounts"],
            ).ask()
            if action == "Go back":
                return
            elif action == "AWS Organizations":
                self.configuration_wizard_aws_organizations()
            elif action == "AWS Accounts":
                self.configuration_wizard_aws_accounts()

    def configuration_wizard_google(self):
        return

    def configuration_wizard_okta(self):
        return

    def configuration_wizard(self):
        while True:
            action = questionary.select(
                "What would you to configure?",
                choices=[
                    "AWS",
                    "Google",
                    "Okta",
                    "Save and Exit",
                    "Exit without saving",
                ],
            ).ask()

            # Let's try really hard not to use a switch statement since it depends on Python 3.10
            if action == "Exit without saving":
                break
            elif action == "Save and Exit":
                self.config.write(self.config_path)
            elif action == "AWS":
                self.configuration_wizard_aws()
            elif action == "Google":
                self.configuration_wizard_google()
            elif action == "Okta":
                self.configuration_wizard_okta()
