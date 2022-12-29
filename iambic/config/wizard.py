from __future__ import annotations

import questionary

from iambic.aws.models import AssumeRoleConfiguration, AWSOrganization, BaseAWSOrgRule
from iambic.config.models import Config
from iambic.core.logger import log


class ConfigurationWizard:
    def __init__(self, config_path: str):
        # TODO: Handle the case where the config file exists but is not valid
        self.config_path = config_path
        try:
            # Try to load a configuration
            self.config: Config = Config.load(config_path)
        except FileNotFoundError:
            # If configuration file doesn't exist, start with an empty configuration
            self.config = Config.construct()
        log.debug("Starting configuration wizard", config_path=config_path)

    def bootstrap_organization(self):
        # bootstraps AWS IAM roles and policies for an organization
        # async def _apply_to_account(  # noqa: C901
        #     self, aws_account: AWSAccount, context: ExecutionContext
        # )
        pass

    def configuration_wizard_aws_accounts(self):
        return self.config

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
            "What is the AWS Organization ID? Usually this looks like `o-123456`"
        ).ask()
        org_name = questionary.text("What is the name of the AWS Organization?").ask()
        org_region = questionary.text(
            "What region is the AWS Organization in? (Such as `us-east-1`)"
        ).ask()

        aws_profile = questionary.text(
            "Is there an AWS profile name (Configured in ~/.aws/config) that Iambic "
            "should use when we access the AWS Organization? Note: "
            "this profile will be used before assuming any subsequent roles. "
            "(If you are using a role with access to the Organization and don't use "
            "a profile, you can leave this blank)"
        ).ask()
        assume_role_arn = questionary.text(
            "What is the role ARN to assume to access the AWS Organization? "
            "(If you are using a role with access to the Organization, you can leave this blank)"
        ).ask()

        default_rule = BaseAWSOrgRule(enabled=True, read_only=False)

        assume_role_arns = AssumeRoleConfiguration(arn=assume_role_arn)

        action = questionary.select(
            "Keep these settings? ",
            choices=["Yes", "No"],
        ).ask()

        if action == "No":
            return

        self.config.aws.organizations.append(
            AWSOrganization(
                org_id=org_id,
                org_name=org_name,
                region=org_region,
                assume_role_arns=assume_role_arn,
                default_rule=default_rule,
            )
        )

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
