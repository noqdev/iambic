from __future__ import annotations

import asyncio
import contextlib
import functools
import os
import re
import select
import sys
from textwrap import dedent
from typing import Union

from aws_error_utils.aws_error_utils import errors
import boto3
import questionary
from botocore.exceptions import ClientError, NoCredentialsError

from iambic.config.dynamic_config import (
    CURRENT_IAMBIC_VERSION,
    Config,
    ExtendsConfig,
    ExtendsConfigKey,
    load_config,
    process_config,
)
from iambic.config.utils import (
    check_and_update_resource_limit,
    resolve_config_template_path,
)
from iambic.core.context import ctx
from iambic.core.iambic_enum import IambicManaged
from iambic.core.logger import log
from iambic.core.template_generation import get_existing_template_map
from iambic.core.utils import yaml
from iambic.github.utils import create_workflow_files
from iambic.plugins.v0_1_0.aws.cloud_formation.utils import (
    create_iambic_eventbridge_stacks,
    create_iambic_role_stacks,
    create_spoke_role_stack,
)
from iambic.plugins.v0_1_0.aws.iam.policy.models import PolicyDocument, PolicyStatement
from iambic.plugins.v0_1_0.aws.iam.role.models import (
    AWS_IAM_ROLE_TEMPLATE_TYPE,
    RoleTemplate,
)
from iambic.plugins.v0_1_0.aws.iam.role.template_generation import (
    generate_aws_role_templates,
)
from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig
from iambic.plugins.v0_1_0.aws.models import (
    ARN_RE,
    IAMBIC_SPOKE_ROLE_NAME,
    AWSAccount,
    AWSIdentityCenter,
    AWSOrganization,
    BaseAWSOrgRule,
    Partition,
    get_hub_role_arn,
    get_spoke_role_arn,
)
from iambic.plugins.v0_1_0.aws.utils import (
    RegionName,
    get_identity_arn,
    is_valid_account_id,
)
from iambic.plugins.v0_1_0.google.iambic_plugin import GoogleConfig, GoogleProject
from iambic.plugins.v0_1_0.okta.iambic_plugin import OktaConfig, OktaOrganization

CUSTOM_AUTO_COMPLETE_STYLE = questionary.Style(
    [
        ("answer", "fg:#0A886A"),
        ("selected", "bold bg:#000000"),
    ]
)


def clear_stdin_buffer():
    """Clears the standard input (stdin) buffer.

    This function reads and discards any input that may be present in the standard
    input (stdin) buffer. This can be useful in cases where previous input may be
    interfering with the desired behavior of a subsequent input operation.

    Args:
        None

    Returns:
        None
    """
    # Warning: This appears to work fine in a real terminal,
    # but not VSCode's Debug Terminal

    r, _, _ = select.select([sys.stdin], [], [], 0)
    while r:
        # If there is input waiting, read and discard it.
        sys.stdin.readline()
        r, _, _ = select.select([sys.stdin], [], [], 0)


def monkeypatch_questionary():
    """Monkeypatches the questionary functions in use to clear stdin buffer."""
    original_functions = {
        "prompt": questionary.prompt,
        "ask": questionary.Question.ask,
        "unsafe_ask": questionary.Question.unsafe_ask,
        "select": questionary.select,
    }

    def patched_function(original_function):
        @functools.wraps(original_function)
        def wrapper(*args, **kwargs):
            clear_stdin_buffer()
            return original_function(*args, **kwargs)

        return wrapper

    for function_name, original_function in original_functions.items():
        setattr(questionary, function_name, patched_function(original_function))


def set_aws_region(question_text: str, default_val: Union[str, RegionName]) -> str:
    default_val = default_val if isinstance(default_val, str) else default_val.value
    choices = [default_val] + [e.value for e in RegionName if e.value != default_val]
    return questionary.select(
        question_text, choices=choices, default=default_val
    ).unsafe_ask()


def set_aws_account_partition(default_val: Union[str, Partition]) -> str:
    return questionary.select(
        "Which AWS partition is the account on?",
        choices=[e.value for e in Partition],
        default=default_val if isinstance(default_val, str) else default_val.value,
    ).unsafe_ask()


def set_aws_role_arn(account_id: str):
    while True:
        role_arn = questionary.text(
            "(Optional) Provide a role arn that CloudFormation will assume to create the stack(s) "
            "or hit enter to use your current access."
        ).unsafe_ask()
        if not role_arn or (account_id in role_arn and re.search(ARN_RE, role_arn)):
            return role_arn or None
        else:
            log.warning(
                "The role ARN must be a valid ARN for the account you are configuring.",
                expected_account_id=account_id,
                provided_role_arn=role_arn,
            )


def set_required_text_value(human_readable_name: str, default_val: str = None):
    while True:
        if response := questionary.text(
            human_readable_name,
            default=default_val or "",
        ).unsafe_ask():
            return response
        else:
            print("Please enter a valid response.")


def set_okta_idp_name(default_val: str = None):
    return set_required_text_value(
        "What is the Okta Identity Provider Name?", default_val
    )


def set_okta_org_url(default_val: str = None):
    return set_required_text_value("What is the Okta Organization URL?", default_val)


def set_okta_api_token(default_val: str = None):
    return set_required_text_value("What is the Okta API Token?", default_val)


def set_google_subject(default_domain: str = None, default_service: str = None) -> dict:
    return {
        "domain": set_required_text_value("What is the Google Domain?", default_domain),
        "service_account": set_required_text_value(
            "What is the Google Service Account?", default_service
        ),
    }


def set_google_project_type(default_val: str = None):
    return set_required_text_value(
        "What is the Google Project Type?", default_val or "service_account"
    )


def set_google_project_id(default_val: str = None):
    return set_required_text_value("What is the Project ID?", default_val)


def set_google_private_key(default_val: str = None):
    return set_required_text_value("What is the Private Key?", default_val)


def set_google_private_key_id(default_val: str = None):
    return set_required_text_value("What is the Private Key ID?", default_val)


def set_google_client_id(default_val: str = None):
    return set_required_text_value("What is the Client ID?", default_val)


def set_google_client_email(default_val: str = None):
    return set_required_text_value("What is the Client E-Mail?", default_val)


def set_google_auth_uri(default_val: str = None):
    return set_required_text_value("What is the Auth URI?", default_val)


def set_google_token_uri(default_val: str = None):
    return set_required_text_value("What is the Token URI?", default_val)


def set_google_auth_provider_cert_url(default_val: str = None):
    return set_required_text_value(
        "What is the auth_provider_x509_cert_url?", default_val
    )


def set_google_client_cert_url(default_val: str = None):
    return set_required_text_value("What is the client_x509_cert_url?", default_val)


def set_identity_center(
    region: str = RegionName.us_east_1,
) -> AWSIdentityCenter:
    identity_center = AWSIdentityCenter()
    identity_center.region = set_aws_region(
        "What region is your Identity Center (SSO) set to?", region
    )
    return identity_center


class ConfigurationWizard:
    def __init__(self, repo_dir: str):
        # TODO: Handle the case where the config file exists but is not valid
        self.default_region = "us-east-1"
        try:
            self.boto3_session = boto3.Session(region_name=self.default_region)
        except Exception as exc:
            log.error(f"Unable to access your AWS account: {exc}")
            sys.exit(1)

        self.autodetected_org_settings = {}
        self.existing_role_template_map = {}
        self.aws_account_map = {}
        self.repo_dir = repo_dir
        self._has_cf_permissions = None
        self._cf_role_arn = None
        self._assume_as_arn = None
        self.caller_identity = {}
        self.profile_name = ""

        asyncio.run(self.set_config_details())

        if self.config.aws:
            self.hub_account_id = self.config.aws.hub_role_arn.split(":")[4]
        else:
            self.hub_account_id = None

        try:
            default_caller_identity = self.boto3_session.client(
                "sts"
            ).get_caller_identity()
            caller_arn = get_identity_arn(default_caller_identity)
            default_hub_account_id = caller_arn.split(":")[4]
        except (AttributeError, IndexError, NoCredentialsError, ClientError, FileNotFoundError):
            default_hub_account_id = None
            default_caller_identity = {}

        if not self.hub_account_id:
            while True:
                self.hub_account_id = set_required_text_value(
                    "To get started with the IAMbic setup wizard, you'll need an AWS account.\n"
                    "This is where IAMbic will deploy its main role. If you have an AWS Organization, "
                    "that account will be your hub account.\n"
                    "Which Account ID should we use to deploy the IAMbic hub role?",
                    default_val=default_hub_account_id,
                )
                if is_valid_account_id(self.hub_account_id):
                    break

        if self.hub_account_id == default_hub_account_id:
            identity_arn = get_identity_arn(default_caller_identity)
            if questionary.confirm(
                f"IAMbic detected you are using {identity_arn} for AWS access.\n"
                f"This identity will require the ability to create"
                f"CloudFormation stacks, stack sets, and stack set instances.\n"
                f"Would you like to use this identity?"
            ).ask():
                self.caller_identity = default_caller_identity
            else:
                self.set_boto3_session()
        else:
            self.set_boto3_session()

        asyncio.run(self.attempt_aws_account_refresh())

        log.debug("Starting configuration wizard", config_path=self.config_path)

    @property
    def has_cf_permissions(self):
        if self._has_cf_permissions is None:
            try:
                self._has_cf_permissions = questionary.confirm(
                    f"This requires that you have the ability to "
                    f"create CloudFormation stacks, stack sets, and stack set instances.\n"
                    f"If you are using an AWS Organization, be sure that trusted access is enabled.\n"
                    f"You can check this using the AWS Console:\n  "
                    f"https://{self.default_region}.console.aws.amazon.com/organizations/v2/home/services/CloudFormation%20StackSets\n"
                    f"Proceed?"
                ).unsafe_ask()
            except KeyboardInterrupt:
                log.info("Exiting...")
                sys.exit(0)

        return self._has_cf_permissions

    @property
    def assume_as_arn(self):
        if self._assume_as_arn is None:
            current_arn = get_identity_arn(self.caller_identity)
            self._assume_as_arn = questionary.text(
                "Provide a user or role ARN that will be able to access the hub role. "
                "Note: Access to this identity is required to use IAMbic locally.",
                default=current_arn,
            ).ask()

        return self._assume_as_arn

    @property
    def cf_role_arn(self):
        if self._cf_role_arn is None:
            self._cf_role_arn = set_aws_role_arn(self.hub_account_id)

        return self._cf_role_arn

    async def set_config_details(self):
        try:
            self.config_path = str((await resolve_config_template_path(self.repo_dir)))
        except RuntimeError:
            self.config_path = f"{self.repo_dir}/iambic_config.yaml"

        if os.path.exists(self.config_path) and os.path.getsize(self.config_path) != 0:
            log.info("Found existing configuration file", config_path=self.config_path)
            try:
                self.config = await load_config(self.config_path)
            except Exception as err:
                log.error(
                    "Unable to load existing configuration file",
                    config_path=self.config_path,
                    error=repr(err),
                )
                sys.exit(1)
        else:
            # Create a stubbed out config file to use for the wizard
            self.config_path = f"{self.repo_dir}/iambic_config.yaml"
            base_config: Config = Config(
                file_path=self.config_path, version=CURRENT_IAMBIC_VERSION
            )

            self.config = await process_config(
                base_config, self.config_path, base_config.dict()
            )

        with contextlib.suppress(ClientError, NoCredentialsError, FileNotFoundError):
            self.autodetected_org_settings = self.boto3_session.client(
                "organizations"
            ).describe_organization()["Organization"]

    def set_aws_profile_name(
        self, question_text: str = None, allow_none: bool = False
    ) -> Union[str, None]:
        available_profiles = self.boto3_session.available_profiles
        if allow_none:
            available_profiles.insert(0, "None")

        if not question_text:
            question_text = dedent(
                f"""
                We couldn't find your AWS credentials, or they're not linked to the Hub Account ({self.hub_account_id}).
                The specified AWS credentials need to be able to create CloudFormation stacks, stack sets,
                and stack set instances.

                Please provide an AWS profile to use for this operation, or restart the wizard with valid AWS credentials: """
            )

        try:
            if len(available_profiles) == 0:
                log.error(
                    "Please create an AWS profile with access to the Hub Account. "
                    "See https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-profiles.html"
                )
                sys.exit(0)
            elif len(available_profiles) < 10:
                profile_name = questionary.select(
                    question_text,
                    choices=available_profiles,
                    default=os.getenv("AWS_PROFILE", ""),
                ).unsafe_ask()
            else:
                profile_name = questionary.autocomplete(
                    question_text,
                    choices=available_profiles,
                    style=CUSTOM_AUTO_COMPLETE_STYLE,
                    default=os.getenv("AWS_PROFILE", ""),
                ).unsafe_ask()
        except KeyboardInterrupt:
            log.info("Exiting...")
            sys.exit(0)

        return profile_name if profile_name != "None" else None

    def set_boto3_session(self):
        self._has_cf_permissions = True
        while True:
            try:
                profile_name = self.set_aws_profile_name()
                self.boto3_session = boto3.Session(
                    profile_name=profile_name, region_name=self.default_region
                )
                self.caller_identity = self.boto3_session.client(
                    "sts"
                ).get_caller_identity()
                selected_hub_account_id = self.caller_identity.get("Arn").split(":")[4]
                if selected_hub_account_id != self.hub_account_id:
                    log.error(
                        "The selected profile does not have access to the Hub Account. Please try again.",
                        required_account_id=self.hub_account_id,
                        selected_account_id=selected_hub_account_id,
                    )
                    continue
            except errors.FileNotFoundError as err:
                log.error(
                    ("We are unable to authenticate to AWS because the provided profile name has a credential_process "
                    "rule setup in your AWS configuration file. Either remove the credential_process rule or use the "
                    "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables."),
                    error=str(err),
                )
                continue
            except errors.ClientError as err:
                log.info(
                    "Unable to create a session for the provided profile name. Please try again.",
                    error=str(err),
                )
                continue
            except errors.ProfileNotFound as err:
                log.info(
                    "Selected profile doesn't exist. Please try again.",
                    error=str(err),
                )
                continue

            self.profile_name = profile_name
            with contextlib.suppress(ClientError, NoCredentialsError, FileNotFoundError):
                self.autodetected_org_settings = self.boto3_session.client(
                    "organizations"
                ).describe_organization()["Organization"]
            break

    def get_boto3_session_for_account(self, account_id: str):
        if account_id == self.hub_account_id:
            if not self.profile_name:
                if profile_name := os.getenv("AWS_PROFILE"):
                    self.profile_name = profile_name
                else:
                    self.profile_name = self.set_aws_profile_name(
                        "Please specify the profile to use to access to the AWS Account.",
                        allow_none=False,
                    )
            return self.boto3_session, self.profile_name
        else:
            profile_name = self.set_aws_profile_name(
                "Please specify the profile to use to access to the AWS Account.\n"
                "If None is selected the AWS Account will be skipped.",
                allow_none=True,
            )
            if not profile_name:
                log.info("Unable to add the AWS Account without a session.")
                return None, None
            return (
                boto3.Session(
                    profile_name=profile_name, region_name=self.default_region
                ),
                profile_name,
            )

    async def attempt_aws_account_refresh(self):
        self.aws_account_map = {}

        if not self.config.aws:
            return

        try:
            await self.config.run_discover_upstream_config_changes(self.repo_dir)
            await self.config.aws.set_identity_center_details()
        except Exception as err:
            log.info("Failed to refresh AWS accounts", error=err)

        self.aws_account_map = {
            account.account_id: account for account in self.config.aws.accounts
        }

    async def save_and_deploy_changes(self, role_template: RoleTemplate):
        log.info(
            "Writing changes locally and deploying updates to AWS",
            role_name=role_template.properties.role_name,
        )

        self.config.write()
        role_template.write(exclude_unset=False)
        await role_template.apply(self.config.aws, ctx)

    def configuration_wizard_aws_account_add(self):  # noqa: C901
        if not self.has_cf_permissions:
            log.info(
                "Unable to edit this attribute without CloudFormation permissions."
            )
            return

        is_hub_account = bool(
            not self.config.aws.accounts and not self.config.aws.organizations
        )
        if is_hub_account:
            account_id = self.hub_account_id
            account_name = set_required_text_value(
                "What is the name of the AWS Account?"
            )
            if not questionary.confirm(
                "Create required Hub and Spoke roles via CloudFormation?\n"
                "The templates that will be used can be found here:\n"
                "  https://github.com/noqdev/iambic/tree/main/iambic/plugins/v0_1_0/aws/cloud_formation/templates"
            ).unsafe_ask():
                log.info(
                    "Unable to add the AWS Account without creating the required roles."
                )
                return
        else:
            account_id = questionary.text(
                "What is the AWS Account ID? Usually this looks like `12345689012`"
            ).unsafe_ask()
            account_name = questionary.text(
                "What is the name of the AWS Account?"
            ).unsafe_ask()
            if not is_valid_account_id(account_id):
                log.info("Invalid AWS Account ID")
                return
            elif account_id in list(self.aws_account_map.keys()):
                log.info("AWS Account already exists in the configuration")
                return

            if not questionary.confirm(
                "Create required Spoke role via CloudFormation?\n"
                "The template that will be used can be found here:\n"
                "  https://github.com/noqdev/iambic/blob/main/iambic/plugins/v0_1_0/aws/cloud_formation/templates/IambicSpokeRole.yml"
            ).unsafe_ask():
                log.info(
                    "Unable to add the AWS account without creating the required role."
                )
                return

        session, profile_name = self.get_boto3_session_for_account(account_id)
        if not session:
            return

        if is_hub_account and not profile_name:
            profile_name = self.profile_name
        elif not is_hub_account:
            profile_name = None

        cf_client = session.client("cloudformation")
        role_arn = set_aws_role_arn(account_id)

        if is_hub_account:
            created_successfully = asyncio.run(
                create_iambic_role_stacks(
                    cf_client=cf_client,
                    hub_account_id=account_id,
                    assume_as_arn=self.assume_as_arn,
                    role_arn=role_arn,
                )
            )
            if not created_successfully:
                log.error("Failed to create the required IAMbic roles. Exiting.")
                sys.exit(0)
        else:
            created_successfully = asyncio.run(
                create_spoke_role_stack(
                    cf_client=cf_client,
                    hub_account_id=account_id,
                    role_arn=role_arn,
                )
            )
            if not created_successfully:
                log.error(
                    "Failed to create the required IAMbic role. Account not added."
                )
                return

        account = AWSAccount(
            account_id=account_id,
            account_name=account_name,
            spoke_role_arn=get_spoke_role_arn(account_id),
            iambic_managed=IambicManaged.READ_AND_WRITE,
            aws_profile=profile_name,
        )
        if is_hub_account:
            account.hub_role_arn = get_hub_role_arn(account_id)
        # account.partition = set_aws_account_partition(account.partition)

        if not questionary.confirm("Keep these settings?").unsafe_ask():
            if questionary.confirm(
                "The AWS account will not be added to the config and wizard will exit. "
                "Proceed?"
            ).unsafe_ask():
                log.info("Exiting")
                sys.exit(0)

        self.config.aws.accounts.append(account)

        if is_hub_account:
            log.info("Importing AWS identities")
            asyncio.run(self.attempt_aws_account_refresh())
            for account in self.config.aws.accounts:
                if account.identity_center_details:
                    asyncio.run(account.set_identity_center_details())
            check_and_update_resource_limit(self.config)
            asyncio.run(
                generate_aws_role_templates(
                    self.config.aws,
                    self.repo_dir,
                )
            )
        else:
            asyncio.run(self.attempt_aws_account_refresh())

    def configuration_wizard_aws_account_edit(self):
        account_names = [account.account_name for account in self.config.aws.accounts]
        account_id_to_config_elem_map = {
            account.account_id: elem
            for elem, account in enumerate(self.config.aws.accounts)
        }
        if len(account_names) > 1:
            action = questionary.autocomplete(
                "Which AWS Account would you like to edit?",
                choices=["Go back", *account_names],
                style=CUSTOM_AUTO_COMPLETE_STYLE,
            ).unsafe_ask()
            if action == "Go back":
                return
            account = next(
                (
                    account
                    for account in self.config.aws.accounts
                    if account.account_name == action
                ),
                None,
            )
            if not account:
                log.debug("Could not find AWS Account")
                return
        else:
            account = self.config.aws.accounts[0]

        choices = ["Go back", "Update IAMbic control"]
        if not account.org_id:
            choices.append("Update name")

        while True:
            action = questionary.select(
                "What would you like to do?",
                choices=choices,
            ).unsafe_ask()
            if action == "Go back":
                return
            elif action == "Update name":
                account.account_name = questionary.text(
                    "What is the name of the AWS Account?",
                    default=account.account_name,
                ).unsafe_ask()

            self.config.aws.accounts[
                account_id_to_config_elem_map[account.account_id]
            ] = account
            self.config.write()

    def configuration_wizard_aws_accounts(self):
        while True:
            if self.config.aws and self.config.aws.accounts:
                action = questionary.select(
                    "What would you like to do?",
                    choices=["Go back", "Add AWS Account", "Edit AWS Account"],
                ).unsafe_ask()
                if action == "Go back":
                    return
                elif action == "Add AWS Account":
                    self.configuration_wizard_aws_account_add()
                elif action == "Edit AWS Account":
                    self.configuration_wizard_aws_account_edit()
            else:
                self.configuration_wizard_aws_account_add()

    def configuration_wizard_aws_organizations_edit(self):
        org_ids = [org.org_id for org in self.config.aws.organizations]
        org_id_to_config_elem_map = {
            org.org_id: elem for elem, org in enumerate(self.config.aws.organizations)
        }
        if len(org_ids) > 1:
            action = questionary.select(
                "Which AWS Organization would you like to edit?",
                choices=["Go back", *org_ids],
            ).unsafe_ask()
            if action == "Go back":
                return
            org_to_edit = next(
                (org for org in self.config.aws.organizations if org.org_id == action),
                None,
            )
            if not org_to_edit:
                log.debug("Could not find AWS Organization to edit", org_id=action)
                return
        else:
            org_to_edit = self.config.aws.organizations[0]

        choices = [
            "Go back",
            "Update IdentityCenter",
            "Update IAMbic control",
        ]
        while True:
            action = questionary.select(
                "What would you like to do?",
                choices=choices,
            ).unsafe_ask()
            if action == "Go back":
                return
            elif action == "Update IdentityCenter":
                org_to_edit.identity_center = set_identity_center(
                    org_to_edit.identity_center.region_name
                )
                asyncio.run(self.attempt_aws_account_refresh())

            self.config.aws.organizations[
                org_id_to_config_elem_map[org_to_edit.org_id]
            ] = org_to_edit
            self.config.write()

    def configuration_wizard_aws_organizations_add(self):
        if not self.has_cf_permissions:
            log.info(
                "Unable to edit this attribute without CloudFormation permissions."
            )
            return

        org_region = "us-east-1"  # Orgs are only available in us-east-1
        org_console_url = f"https://{org_region}.console.aws.amazon.com/organizations/v2/home/accounts"
        org_id = questionary.text(
            f"What is the AWS Organization ID? It can be found here {org_console_url}",
            default=self.autodetected_org_settings.get("Id", ""),
        ).unsafe_ask()

        account_id = self.hub_account_id
        session, profile_name = self.get_boto3_session_for_account(account_id)
        if not session:
            return

        if not questionary.confirm(
            "Create required Hub and Spoke roles via CloudFormation?\n"
            "The templates that will be used can be found here:\n"
            "  https://github.com/noqdev/iambic/tree/main/iambic/plugins/v0_1_0/aws/cloud_formation/templates"
        ).unsafe_ask():
            log.info("Unable to add the AWS Org without creating the required roles.")
            return

        created_successfully = asyncio.run(
            create_iambic_role_stacks(
                cf_client=session.client("cloudformation"),
                hub_account_id=account_id,
                assume_as_arn=self.assume_as_arn,
                role_arn=self.cf_role_arn,
                org_client=session.client("organizations"),
            )
        )
        if not created_successfully:
            log.error("Failed to create the required IAMbic roles. Exiting.")
            sys.exit(0)

        aws_org = AWSOrganization(
            org_id=org_id,
            org_account_id=account_id,
            region=org_region,
            default_rule=BaseAWSOrgRule(),
            hub_role_arn=get_hub_role_arn(account_id),
            aws_profile=profile_name,
        )
        aws_org.default_rule.iambic_managed = IambicManaged.READ_AND_WRITE

        self.config.aws.organizations.append(aws_org)

        log.debug("Attempting to get a session on the AWS org", org_id=org_id)
        try:
            session = asyncio.run(aws_org.get_boto3_session())
        except ClientError as e:
            log.error("Unable to get a session on the AWS org", org_id=org_id, error=e)
            session = None

        if (
            session
            and questionary.confirm(
                "Would you like to setup Identity Center (SSO) support?", default=False
            ).unsafe_ask()
        ):
            aws_org.identity_center = set_identity_center()

        if not questionary.confirm("Keep these settings?").unsafe_ask():
            if questionary.confirm(
                "The AWS Org will not be added to the config and wizard will exit. "
                "Proceed?"
            ).unsafe_ask():
                log.info("Exiting")
                sys.exit(0)

        log.info("Saving config.")
        self.config.write()

        if not questionary.confirm(
            "Add the org accounts to the config and import the org's AWS identities?"
        ).unsafe_ask():
            if questionary.confirm(
                "This is required to finish the setup process. Wizard will exit if this has not been setup. "
                "Exit?"
            ).unsafe_ask():
                log.info("Exiting")
                sys.exit(0)

        asyncio.run(self.attempt_aws_account_refresh())

    def configuration_wizard_aws_organizations(self):
        # Currently only 1 org per config is supported.
        if questionary.confirm(
            "If you would like to use AWS Organizations, the IAMbic hub account you configured must be in the same "
            "AWS account as your AWS Organization.\nIs this the case?"
        ).unsafe_ask():
            if self.config.aws and self.config.aws.organizations:
                self.configuration_wizard_aws_organizations_edit()
            else:
                self.configuration_wizard_aws_organizations_add()

    def configuration_wizard_aws(self):
        while True:
            action = questionary.select(
                "What would you like to configure in AWS?\n"
                "We recommend configuring IAMbic with AWS Organizations, "
                "but you may also manually configure accounts.",
                choices=["Go back", "AWS Organizations", "AWS Accounts"],
            ).unsafe_ask()
            if action == "Go back":
                return
            elif action == "AWS Organizations":
                self.configuration_wizard_aws_organizations()
            elif action == "AWS Accounts":
                self.configuration_wizard_aws_accounts()

    def create_secret(self):
        region = set_aws_region(
            "What region should the secret be created in?",
            self.default_region,
        )

        role_arn = get_spoke_role_arn(self.hub_account_id)

        question_text = "Create the secret"
        role_name = IAMBIC_SPOKE_ROLE_NAME
        role_account_id = self.hub_account_id

        if role_name:
            question_text += f" and update the {role_name} IAMbic template"

        if not questionary.confirm(f"{question_text}?").unsafe_ask():
            self.config.secrets = {}
            return

        if role_name and (aws_account := self.aws_account_map.get(role_account_id)):
            session = asyncio.run(aws_account.get_boto3_session(region_name=region))
        else:
            session = boto3.Session(region_name=region)

        client = session.client(service_name="secretsmanager")
        response = client.create_secret(
            Name="iambic-config-secrets",
            Description="IAMbic managed secret used to store protected config values",
            SecretString=yaml.dump({"secrets": self.config.secrets}),
        )

        self.config.extends = [
            ExtendsConfig(
                key=ExtendsConfigKey.AWS_SECRETS_MANAGER,
                value=response["ARN"],
                assume_role_arn=role_arn,
            )
        ]
        self.config.write()

        if role_arn:
            role_template: RoleTemplate = self.existing_role_template_map.get(role_name)
            role_template.properties.inline_policies.append(
                PolicyDocument(
                    policy_name="read_iambic_secrets",
                    included_accounts=[role_account_id],
                    statement=[
                        PolicyStatement(
                            effect="Allow",
                            action=[
                                "secretsmanager:GetSecretValue",
                                "secretsmanager:PutSecretValue",
                            ],
                            resource=[response["ARN"]],
                        )
                    ],
                )
            )
            asyncio.run(self.save_and_deploy_changes(role_template))

    def update_secret(self):
        if not self.config.secrets:
            self.config.secrets = {}
        if self.config.okta:
            self.config.secrets.setdefault("okta", {})["organizations"] = [
                org.dict() for org in self.config.okta.organizations
            ]

        if self.config.google:
            self.config.secrets.setdefault("google", {})["projects"] = [
                project.dict(
                    include={
                        "subjects",
                        "type",
                        "project_id",
                        "private_key_id",
                        "private_key",
                        "client_email",
                        "client_id",
                        "auth_uri",
                        "token_uri",
                        "auth_provider_x509_cert_url",
                        "client_x509_cert_url",
                    }
                )
                for project in self.config.google.projects
            ]

        secret_details = self.config.extends[0]
        secret_arn = secret_details.value
        region = secret_arn.split(":")[3]
        secret_account_id = secret_arn.split(":")[4]

        if aws_account := self.aws_account_map.get(secret_account_id):
            session = asyncio.run(aws_account.get_boto3_session(region_name=region))
        else:
            session = boto3.Session(region_name=region)

        client = session.client(service_name="secretsmanager")
        client.put_secret_value(
            SecretId=secret_arn,
            SecretString=yaml.dump({"secrets": self.config.secrets}),
        )

    def configuration_wizard_google_project_add(self):
        google_obj = {
            "subjects": [set_google_subject()],
            "type": set_google_project_type(),
            "project_id": set_google_project_id(),
            "private_key_id": set_google_private_key_id(),
            "private_key": set_google_private_key(),
            "client_email": set_google_client_email(),
            "client_id": set_google_client_id(),
            "auth_uri": set_google_auth_uri(),
            "token_uri": set_google_token_uri(),
            "auth_provider_x509_cert_url": set_google_auth_provider_cert_url(),
            "client_x509_cert_url": set_google_client_cert_url(),
        }
        if self.config.secrets:
            self.config.secrets.setdefault("google", {}).setdefault(
                "projects", []
            ).append(google_obj)
            self.config.google = GoogleConfig(projects=[GoogleProject(**google_obj)])
            self.update_secret()
        else:
            self.config.secrets = {"google": {"projects": [google_obj]}}
            self.create_secret()

    def configuration_wizard_google_project_edit(self):
        project_ids = [project.project_id for project in self.config.google.projects]
        project_id_to_config_elem_map = {
            project.project_id: elem
            for elem, project in enumerate(self.config.google.projects)
        }
        if len(project_ids) > 1:
            action = questionary.select(
                "Which Google Project would you like to edit?",
                choices=["Go back", *project_ids],
            ).unsafe_ask()
            if action == "Go back":
                return
            project_to_edit = next(
                (
                    project
                    for project in self.config.google.projects
                    if project.project_id == action
                ),
                None,
            )
            if not project_to_edit:
                log.debug("Could not find AWS Organization to edit", org_id=action)
                return
        else:
            project_to_edit = self.config.google.projects[0]

        project_id = project_to_edit.project_id
        choices = [
            "Go back",
            "Update Subject",
            "Update Type",
            "Update Private Key" "Update Private Key ID",
            "Update Client Email",
            "Update Client ID",
            "Update Auth URI",
            "Update Token URI",
            "Update Auth Provider Cert URL",
            "Update Client Cert URL",
        ]
        while True:
            action = questionary.select(
                "What would you like to do?",
                choices=choices,
            ).unsafe_ask()
            if action == "Go back":
                return
            elif action == "Update Subject":
                if project_to_edit.subjects:
                    default_domain = project_to_edit.subjects[0].domain
                    default_service = project_to_edit.subjects[0].service_account
                else:
                    default_domain = None
                    default_service = None
                project_to_edit.subjects = [
                    set_google_subject(default_domain, default_service)
                ]
            elif action == "Update Type":
                project_to_edit.type = set_google_project_type(project_to_edit.type)
            elif action == "Update Private Key":
                project_to_edit.private_key = set_google_private_key(
                    project_to_edit.private_key
                )
            elif action == "Update Private Key ID":
                project_to_edit.private_key_id = set_google_private_key_id(
                    project_to_edit.private_key_id
                )
            elif action == "Update Client Email":
                project_to_edit.client_email = set_google_client_email(
                    project_to_edit.client_email
                )
            elif action == "Update Client ID":
                project_to_edit.client_id = set_google_client_id(
                    project_to_edit.client_id
                )
            elif action == "Update Auth URI":
                project_to_edit.auth_uri = set_google_auth_uri(project_to_edit.auth_uri)
            elif action == "Update Token URI":
                project_to_edit.token_uri = set_google_token_uri(
                    project_to_edit.token_uri
                )
            elif action == "Update Auth Provider Cert URL":
                project_to_edit.auth_provider_x509_cert_url = (
                    set_google_auth_provider_cert_url(
                        project_to_edit.auth_provider_x509_cert_url
                    )
                )
            elif action == "Update Client Cert URL":
                project_to_edit.client_x509_cert_url = set_google_client_cert_url(
                    project_to_edit.client_x509_cert_url
                )

            self.config.google.projects[
                project_id_to_config_elem_map[project_id]
            ] = project_to_edit
            self.update_secret()
            self.config.write()

    def configuration_wizard_google(self):
        log.info(
            "For details on how to retrieve the information required to add a Google Project "
            "to IAMbic check out our docs: https://iambic.org/getting_started/google/"
        )

        if self.config.google:
            action = questionary.select(
                "What would you like to do?",
                choices=["Go back", "Add", "Edit"],
            ).unsafe_ask()
            if action == "Go back":
                return
            elif action == "Add":
                self.configuration_wizard_google_project_add()
            elif action == "Edit":
                self.configuration_wizard_google_project_edit()
        else:
            self.configuration_wizard_google_project_add()

    def configuration_wizard_okta_organization_add(self):
        okta_obj = {
            "idp_name": set_okta_idp_name(),
            "org_url": set_okta_org_url(),
            "api_token": set_okta_api_token(),
        }
        if self.config.secrets:
            self.config.secrets.setdefault("okta", {}).setdefault(
                "organizations", []
            ).append(okta_obj)
            self.config.okta = OktaConfig(organizations=[OktaOrganization(**okta_obj)])
            self.update_secret()
        else:
            self.config.secrets = {"okta": {"organizations": [okta_obj]}}
            self.create_secret()

    def configuration_wizard_okta_organization_edit(self):
        org_names = [org.idp_name for org in self.config.okta.organizations]
        org_name_to_config_elem_map = {
            org.idp_name: elem
            for elem, org in enumerate(self.config.okta.organizations)
        }
        if len(org_names) > 1:
            action = questionary.select(
                "Which Okta Organization would you like to edit?",
                choices=["Go back", *org_names],
            ).unsafe_ask()
            if action == "Go back":
                return
            org_to_edit = next(
                (
                    org
                    for org in self.config.okta.organizations
                    if org.idp_name == action
                ),
                None,
            )
            if not org_to_edit:
                log.debug("Could not find Okta Organization to edit", idp_name=action)
                return
        else:
            org_to_edit = self.config.okta.organizations[0]

        org_name = org_to_edit.idp_name
        choices = [
            "Go back",
            "Update name",
            "Update Organization URL",
            "Update API Token",
        ]
        while True:
            action = questionary.select(
                "What would you like to do?",
                choices=choices,
            ).unsafe_ask()
            if action == "Go back":
                return
            elif action == "Update name":
                org_to_edit.idp_name = set_okta_idp_name(org_to_edit.idp_name)
            elif action == "Update Organization URL":
                org_to_edit.org_url = set_okta_org_url(org_to_edit.org_url)
            elif action == "Update API Token":
                org_to_edit.api_token = set_okta_api_token(org_to_edit.api_token)

            self.config.okta.organizations[
                org_name_to_config_elem_map[org_name]
            ] = org_to_edit
            self.update_secret()
            self.config.write()

    def configuration_wizard_okta(self):
        log.info(
            "For details on how to retrieve the information required to add an Okta Organization "
            "to IAMbic check out our docs: https://iambic.org/getting_started/okta/"
        )
        if self.config.okta:
            action = questionary.select(
                "What would you like to do?",
                choices=["Go back", "Add", "Edit"],
            ).unsafe_ask()
            if action == "Go back":
                return
            elif action == "Add":
                self.configuration_wizard_okta_organization_add()
            elif action == "Edit":
                self.configuration_wizard_okta_organization_edit()
        else:
            self.configuration_wizard_okta_organization_add()

    def configuration_wizard_github_workflow(self):
        log.info(
            "NOTE: Currently, only GitHub Workflows are supported. "
            "However, you can modify the generated output to work with your Git provider."
        )

        if questionary.confirm("Proceed?").unsafe_ask():
            commit_email = set_required_text_value(
                "What is the E-Mail address to use for commits?"
            )
            repo_name = set_required_text_value(
                "What is the name of the repository, including the organization (example: github_org/repo_name)?"
            )
            if self.config.aws and self.config.aws.organizations:
                aws_org = self.config.aws.organizations[0]
                region = aws_org.region_name
            else:
                region = set_aws_region(
                    "What AWS region should the workflow run in?",
                    default_val=RegionName.us_east_1,
                )

            create_workflow_files(
                repo_dir=self.repo_dir,
                repo_name=repo_name,
                commit_email=commit_email,
                assume_role_arn=self.config.aws.hub_role_arn,
                region=region,
            )

    def configuration_wizard_change_detection_setup(self, aws_org: AWSOrganization):
        if not questionary.confirm(
            "To setup change detection for iambic requires "
            "creating CloudFormation stacks "
            "and a CloudFormation stack set.\n"
            "This will also update the IAMbic Hub Role to add the required policy to consume the changes.\n"
            "Proceed?"
        ).unsafe_ask():
            return

        session, _ = self.get_boto3_session_for_account(aws_org.org_account_id)
        cf_client = session.client("cloudformation", region_name="us-east-1")
        org_client = session.client("organizations", region_name="us-east-1")

        successfully_created = asyncio.run(
            create_iambic_eventbridge_stacks(
                cf_client,
                org_client,
                aws_org.org_id,
                aws_org.org_account_id,
                self.cf_role_arn,
            )
        )
        if not successfully_created:
            return

        role_name = IAMBIC_SPOKE_ROLE_NAME
        hub_account_id = self.hub_account_id
        sqs_arn = f"arn:aws:sqs:us-east-1:{hub_account_id}:IAMbicChangeDetectionQueue"
        role_template: RoleTemplate = self.existing_role_template_map.get(role_name)
        role_template.properties.inline_policies.append(
            PolicyDocument(
                policy_name="consume_iambic_changes",
                included_accounts=[hub_account_id],
                statement=[
                    PolicyStatement(
                        effect="Allow",
                        action=[
                            "sqs:DeleteMessage",
                            "sqs:ReceiveMessage",
                            "sqs:GetQueueAttributes",
                        ],
                        resource=[sqs_arn],
                    )
                ],
            )
        )

        self.config.aws.sqs_cloudtrail_changes_queues = [sqs_arn]
        asyncio.run(self.save_and_deploy_changes(role_template))

    def run(self):  # noqa: C901
        if "aws" not in self.config.__fields__:
            log.info("The config wizard requires the IAMbic AWS plugin.")
            return
        elif not self.config.aws:
            self.config.aws = AWSConfig()

        while True:
            choices = ["AWS", "Done"]
            secret_in_config = bool(self.config.extends)
            if secret_in_config:
                secret_question_text = "This requires the ability to update the AWS Secrets Manager secret."
            else:
                secret_question_text = "This requires permissions to update a role and create an AWS Secret."

            if self.config.aws.accounts or self.config.aws.organizations:
                if not self.existing_role_template_map:
                    log.info("Loading AWS role templates...")
                    self.existing_role_template_map = asyncio.run(
                        get_existing_template_map(
                            self.repo_dir, AWS_IAM_ROLE_TEMPLATE_TYPE
                        )
                    )
                if self.existing_role_template_map:
                    choices = ["AWS"]
                    # Currently, the config wizard only support IAMbic plugins
                    if "google" in self.config.__fields__:
                        choices.append("Google")
                    if "okta" in self.config.__fields__:
                        choices.append("Okta")

                    choices.extend(["Generate Github Action Workflows", "Done"])

                if (
                    self.config.aws.organizations
                    and self.existing_role_template_map
                    and not self.config.aws.sqs_cloudtrail_changes_queues
                ):
                    choices.insert(-1, "Setup AWS change detection")

            try:
                action = questionary.select(
                    "What would you like to configure?",
                    choices=choices,
                ).unsafe_ask()
            except KeyboardInterrupt:
                log.info("Exiting...")
                return

            # Let's try really hard not to use a switch statement since it depends on Python 3.10
            try:
                if action == "Done":
                    self.config.write()
                    return
                elif action == "AWS":
                    self.configuration_wizard_aws()
                elif action == "Google":
                    if questionary.confirm(
                        f"{secret_question_text} Proceed?"
                    ).unsafe_ask():
                        self.configuration_wizard_google()
                elif action == "Okta":
                    if questionary.confirm(
                        f"{secret_question_text} Proceed?"
                    ).unsafe_ask():
                        self.configuration_wizard_okta()
                elif action == "Generate Github Action Workflows":
                    self.configuration_wizard_github_workflow()
                elif action == "Setup AWS change detection":
                    if self.has_cf_permissions:
                        log.info(
                            f"IAMbic change detection relies on CloudTrail being enabled all IAMbic aware accounts. "
                            f"You can check that you have CloudTrail setup by going to "
                            f"https://{self.default_region}.console.aws.amazon.com/cloudtrail/home\n"
                            f"If you do not have CloudTrail setup, you can set it up by going to "
                            f"https://{self.default_region}.console.aws.amazon.com/cloudtrail/home?region={self.default_region}#/create"
                        )
                        self.configuration_wizard_change_detection_setup(
                            self.config.aws.organizations[0]
                        )
                    else:
                        log.info(
                            "Unable to edit this attribute without CloudFormation permissions."
                        )
            except KeyboardInterrupt:
                ...


monkeypatch_questionary()
