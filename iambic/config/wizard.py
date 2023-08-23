from __future__ import annotations

import asyncio
import contextlib
import functools
import json
import os
import re
import select
import sys
import time
import uuid
import webbrowser
from enum import Enum
from pathlib import Path
from typing import Optional, Union

import boto3
import click
import questionary
from aws_error_utils.aws_error_utils import errors
from botocore.exceptions import ClientError, NoCredentialsError
from pydantic.json import pydantic_encoder
from pydantic.types import SecretStr

from iambic.config.dynamic_config import (
    CURRENT_IAMBIC_VERSION,
    Config,
    ExtendsConfig,
    ExtendsConfigKey,
    load_config,
    process_config,
)
from iambic.config.utils import (
    aws_cf_parse_key_value_string,
    check_and_update_resource_limit,
    resolve_config_template_path,
    validate_aws_cf_input_tags,
)
from iambic.core.context import ctx
from iambic.core.iambic_enum import Command, IambicManaged
from iambic.core.logger import log
from iambic.core.models import ExecutionMessage
from iambic.core.parser import load_templates
from iambic.core.template_generation import get_existing_template_map
from iambic.core.utils import gather_templates, yaml
from iambic.plugins.v0_1_0.aws.cloud_formation.utils import (
    create_github_app_code_build_stack,
    create_github_app_ecr_pull_through_cache_stack,
    create_github_app_ecr_repo_stack,
    create_github_app_lambda_stack,
    create_github_app_roles_stack,
    create_iambic_eventbridge_stacks,
    create_iambic_role_stacks,
    create_spoke_role_stack,
)
from iambic.plugins.v0_1_0.aws.handlers import apply as aws_apply
from iambic.plugins.v0_1_0.aws.handlers import import_aws_resources
from iambic.plugins.v0_1_0.aws.handlers import load as aws_load
from iambic.plugins.v0_1_0.aws.iam.role.models import (
    AWS_IAM_ROLE_TEMPLATE_TYPE,
    AwsIamRoleTemplate,
)
from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig
from iambic.plugins.v0_1_0.aws.models import (
    ARN_RE,
    IAMBIC_CHANGE_DETECTION_SUFFIX,
    IAMBIC_HUB_ROLE_NAME,
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
from iambic.plugins.v0_1_0.azure_ad.handlers import import_azure_ad_resources
from iambic.plugins.v0_1_0.azure_ad.iambic_plugin import AzureADConfig
from iambic.plugins.v0_1_0.azure_ad.models import AzureADOrganization
from iambic.plugins.v0_1_0.github.create_github_app import (
    get_github_app_installations,
    get_repos_for_installation,
)
from iambic.plugins.v0_1_0.google_workspace.handlers import import_google_resources
from iambic.plugins.v0_1_0.google_workspace.iambic_plugin import (
    GoogleProject,
    GoogleSubject,
    GoogleWorkspaceConfig,
)
from iambic.plugins.v0_1_0.okta.handlers import import_okta_resources
from iambic.plugins.v0_1_0.okta.iambic_plugin import OktaConfig, OktaOrganization

AWS_SECRETS = "AWS Secrets"
LOCALLY = "Locally"

CUSTOM_AUTO_COMPLETE_STYLE = questionary.Style(
    [
        ("answer", "fg:#0A886A"),
        ("selected", "bold bg:#000000"),
    ]
)


class Operation(Enum):
    ADDED = "added"
    UPDATED = "updated"
    DELETED = "deleted"


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

    # Adding os check if windows then disabling this code as
    # it is causing an error
    if os.name != "nt":
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


def get_secret_dict_with_val(pydantic_model, **kwargs) -> dict:
    def show_secrets_encoder(obj):
        if isinstance(obj, SecretStr):
            return obj.get_secret_value()
        else:
            return pydantic_encoder(obj)

    return json.loads(pydantic_model.json(encoder=show_secrets_encoder, **kwargs))


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
        click.echo(
            "\n(Optional) Provide a role arn that CloudFormation will assume to create the stack(s) "
            "or hit enter to use your current access."
        )
        role_arn = questionary.text("(Optional) Role ARN").unsafe_ask()
        if not role_arn or (account_id in role_arn and re.search(ARN_RE, role_arn)):
            return role_arn or None
        else:
            log.warning(
                "The role ARN must be a valid ARN for the account you are configuring.",
                expected_account_id=account_id,
                provided_role_arn=role_arn,
            )


def set_aws_is_read_only() -> bool:
    click.echo(
        "\nGrant IambicSpokeRole write access to IAM and IdentityCenter?\n"
        "If set to 'no', this will limit IAMbic's capabilities to import-only."
    )
    return not bool(
        questionary.confirm(
            "Grant IambicSpokeRole write access?",
            default=True,
        ).unsafe_ask()
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


def set_required_secure_text_value(
    human_readable_name: str,
    default_val: Optional[SecretStr] = None,
):
    while True:
        if response := questionary.text(
            human_readable_name,
            default=SecretStr(default_val or "").get_secret_value(),
        ).unsafe_ask():
            return SecretStr(response.replace("\\n", "\n"))
        else:
            print("Please enter a valid response.")


def set_idp_name(default_val: str = None):
    return set_required_text_value("What is the Identity Provider Name?", default_val)


def set_tenant_id(default_val: str = None):
    return set_required_text_value("What is the Tenant ID?", default_val)


def set_client_id(default_val: str = None):
    return set_required_text_value("What is the Client ID?", default_val)


def set_client_secret(default_val: str = None):
    return set_required_text_value("What is the Client Secret?", default_val)


def set_okta_org_url(default_val: str = None):
    return set_required_text_value("What is the Organization URL?", default_val)


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


def set_google_private_key(default_val: SecretStr = None):
    return set_required_secure_text_value("What is the Private Key?", default_val)


def set_google_private_key_id(default_val: str = None):
    return set_required_text_value("What is the Private Key ID?", default_val)


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


def confirm_command_exe(
    provider_type: str, operation: Operation, requires_sync: bool = False
):
    command_type = "import"
    if requires_sync:
        command_type = (
            "an apply of applicable templates that are NOT in the account and an import"
        )

    if operation == Operation.ADDED:
        operation_str = f"{operation.value} to"
    elif operation == Operation.UPDATED:
        operation_str = f"{operation.value} in"
    elif operation == Operation.DELETED:
        operation_str = f"{operation.value} from"
    else:
        raise ValueError(f"Invalid operation: {operation}")

    click.echo(
        f"\nTo preserve these changes, {command_type} must be run to sync your templates."
    )
    if not questionary.confirm("Proceed?").unsafe_ask():
        click.echo(
            f"\nThe {provider_type} will not be {operation_str} the config and wizard will exit."
        )
        if questionary.confirm("Proceed?").unsafe_ask():
            log.info("Exiting...")
            sys.exit(0)


class ConfigurationWizard:
    def __init__(self, repo_dir: str, is_more_options: bool = False):
        # TODO: Handle the case where the config file exists but is not valid
        self.existing_role_template_map = {}
        self.aws_account_map = {}
        self.repo_dir = repo_dir
        self._has_cf_stacksets_permissions = None
        self._has_confirm_cf_permissions = None
        self._cf_role_arn = None
        self._assume_as_arn = None
        self.caller_identity = {}
        self.profile_name = ""
        self._default_region = None
        self._is_more_options = is_more_options

        asyncio.run(self.set_config_details())
        check_and_update_resource_limit(self.config)
        log.debug("Starting configuration wizard", config_path=self.config_path)

    def _reset_cf_stacksets_known_states(self):
        # call this if you want to bust the previous known states whether
        # the user has CF StackSets permissions.
        self._has_cf_stacksets_permissions = None

    @property
    def has_cf_stacksets_permissions(self):
        if self._has_cf_stacksets_permissions is None:
            try:
                with contextlib.suppress(
                    ClientError, NoCredentialsError, FileNotFoundError
                ):
                    cf_client = self.boto3_session.client(
                        "cloudformation", self.aws_default_region
                    )
                    cf_response = cf_client.describe_organizations_access()
                    self._has_cf_stacksets_permissions = (
                        cf_response["Status"] == "ENABLED"
                    )

                    org_client = self.boto3_session.client("organizations")
                    self.autodetected_org_settings = org_client.describe_organization()[
                        "Organization"
                    ]
                    if self._has_cf_stacksets_permissions:
                        return self._has_cf_stacksets_permissions

                # Try turning it on for the user
                with contextlib.suppress(
                    ClientError, NoCredentialsError, FileNotFoundError
                ):
                    cf_client = self.boto3_session.client(
                        "cloudformation", self.aws_default_region
                    )
                    _ = cf_client.activate_organizations_access()
                    log.info(
                        "We have activated Organization Access for CloudFormation StackSets"
                    )
                    cf_response = cf_client.describe_organizations_access()
                    self._has_cf_stacksets_permissions = (
                        cf_response["Status"] == "ENABLED"
                    )
                    if self._has_cf_stacksets_permissions:
                        return self._has_cf_stacksets_permissions

                click.echo(
                    "\nThis requires that you have the ability to "
                    "create CloudFormation stacks, stack sets, and stack set instances.\n"
                    "If you are using an AWS Organization, be sure that trusted access is enabled.\n"
                    "You can check this using the AWS Console:\n  "
                    "https://us-east-1.console.aws.amazon.com/organizations/v2/home/services/CloudFormation%20StackSets"
                )
                if self._has_cf_stacksets_permissions is None:
                    self._has_cf_stacksets_permissions = questionary.confirm(
                        "Proceed?"
                    ).unsafe_ask()
            except KeyboardInterrupt:
                log.info("Exiting...")
                sys.exit(0)

        return self._has_cf_stacksets_permissions

    @property
    def has_confirm_cf_permissions(self):
        if self._has_confirm_cf_permissions is None:
            try:
                click.echo(
                    "\nThis requires that you have the ability to "
                    "create CloudFormation stacks\n"
                )
                if self._has_confirm_cf_permissions is None:
                    self._has_confirm_cf_permissions = questionary.confirm(
                        "Proceed?"
                    ).unsafe_ask()
            except KeyboardInterrupt:
                log.info("Exiting...")
                sys.exit(0)

        return self._has_confirm_cf_permissions

    @property
    def assume_as_arn(self):
        if self._assume_as_arn is None:
            current_arn = get_identity_arn(self.caller_identity)
            click.echo(
                "\nProvide the ARN of the identity (e.g. IAM User, Group, or Role) "
                "that will be able to access the hub role.\n"
                "Note: Access to this identity is required to use IAMbic locally.",
            )
            self._assume_as_arn = questionary.text(
                "Identity ARN",
                default=current_arn,
            ).ask()

        return self._assume_as_arn

    @property
    def cf_role_arn(self):
        if self._cf_role_arn is None:
            self._cf_role_arn = set_aws_role_arn(self.hub_account_id)

        return self._cf_role_arn

    @property
    def has_aws_account_or_organizations(self) -> bool:
        return (
            hasattr(self, "config")
            and self.config.aws
            and (self.config.aws.accounts or self.config.aws.organizations)
        )

    @property
    def aws_default_region(self) -> str:
        default_val = RegionName.us_east_1.value

        if self._default_region:
            return self._default_region
        elif self.has_aws_account_or_organizations:
            if self.config.aws.organizations:
                self._default_region = self.config.aws.organizations[0].region_name
            else:
                hub_account = [
                    account
                    for account in self.config.aws.accounts
                    if account.hub_role_arn
                ]
                if hub_account:
                    self._default_region = hub_account[0].region_name
                else:
                    self._default_region = set_aws_region(
                        "What region should IAMbic use?", default_val
                    )
        else:
            self._default_region = set_aws_region(
                "What region should IAMbic use?", default_val
            )

        return self._default_region

    @property
    def secrets_message(self) -> tuple[str, bool]:
        """Returns if secrets are configured"""
        secret_in_config = bool(self.config.extends)

        if (
            secret_in_config
            and self.config.extends[0].key == ExtendsConfigKey.AWS_SECRETS_MANAGER
        ):
            secret_question_text = (
                "This requires the ability to update the AWS Secrets Manager secret."
            )
        elif (
            secret_in_config
            and self.config.extends[0].key == ExtendsConfigKey.LOCAL_FILE
        ):
            secret_question_text = (
                "This requires permissions to update secrets in your secrets file."
            )
        else:
            secret_question_text = "Secrets must be created."

        return (secret_question_text, secret_in_config)

    @property
    def has_okta_configured(self) -> bool:
        return self.config.okta and self.config.okta.organizations

    def secret_config_dir(self, secrets_file: str = "secrets.yaml") -> str:
        return f"{Path(self.config_path).parent.joinpath(secrets_file)}"

    async def set_config_details(self):
        self.config_path = await self._get_config_path()

        if os.path.exists(self.config_path) and os.path.getsize(self.config_path) != 0:
            log.info("Found existing configuration file", config_path=self.config_path)
            self.config = await load_config(self.config_path)
        else:
            # Create a stubbed out config file to use for the wizard
            self.config_path = f"{self.repo_dir}/iambic_config.yaml"
            base_config: Config = Config(
                file_path=self.config_path, version=CURRENT_IAMBIC_VERSION
            )

            self.config = await process_config(
                base_config, self.config_path, base_config.dict()
            )

    async def _get_config_path(self):
        try:
            config_path = str((await resolve_config_template_path(self.repo_dir)))
        except RuntimeError:
            config_path = f"{self.repo_dir}/iambic_config.yaml"
        return config_path

    def resolve_aws_profile_defaults_from_env(self) -> str:
        if "AWS_ACCESS_KEY_ID" in os.environ:
            # Environment variables has 1st priority
            profile_name = "None"
            log.info("Using AWS credentials from environment", profile=profile_name)
        elif profile_name := os.environ.get("AWS_PROFILE"):
            # Explicit profile has 2nd priority
            log.info("Using AWS profile from environment", profile=profile_name)
        elif profile_name := os.environ.get("AWS_DEFAULT_PROFILE"):
            # Fallback profile has 3rd priority
            log.info("Using AWS default profile from environment", profile=profile_name)
        else:
            # User has to direct the wizard at this point since
            # we cannot reason what credential to use.
            profile_name = "None"
            log.info(
                "Not able detect a standard credential provider chain",
                profile=profile_name,
            )

        return profile_name

    def set_aws_profile_name(
        self, question_text: str = None, allow_none: bool = False
    ) -> Union[str, None]:
        questionary_params = {}
        boto3_session = boto3.Session(region_name=self.aws_default_region)
        available_profiles = boto3_session.available_profiles
        if allow_none:
            available_profiles.insert(0, "None")

        default_profile = self.resolve_aws_profile_defaults_from_env()
        if default_profile != "None":
            questionary_params["default"] = default_profile
            available_profiles.append(default_profile)

        if not question_text:
            click.echo(
                f"\nWe couldn't find your AWS credentials, or they're not linked to the Hub Account ({self.hub_account_id}). "
                "The specified AWS credentials need to be able to create CloudFormation stacks, stack sets, and stack set instances. "
                "Please provide an AWS profile to use for this operation or restart the wizard with valid AWS credentials."
            )
            question_text = "AWS Profile"

        try:
            if len(available_profiles) == 0:
                log.error(
                    "Please create an AWS profile with access to the Hub Account. "
                    "See https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-profiles.html"
                )
                sys.exit(0)
            elif len(available_profiles) < 10:
                profile_name = questionary.select(
                    question_text, choices=available_profiles, **questionary_params
                ).unsafe_ask()
            else:
                profile_name = questionary.autocomplete(
                    question_text,
                    choices=available_profiles,
                    style=CUSTOM_AUTO_COMPLETE_STYLE,
                    **questionary_params,
                ).unsafe_ask()
        except KeyboardInterrupt:
            log.info("Exiting...")
            sys.exit(0)

        return profile_name if profile_name != "None" else None

    def set_boto3_session(self, allow_none=False):
        while True:
            try:
                profile_name = self.set_aws_profile_name(allow_none=allow_none)
                self.boto3_session = boto3.Session(
                    profile_name=profile_name, region_name=self.aws_default_region
                )
                self.caller_identity = self.boto3_session.client(
                    "sts", region_name=self.aws_default_region
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
                    (
                        "We are unable to authenticate to AWS because the provided profile name has a credential_process "
                        "rule setup in your AWS configuration file. Either remove the credential_process rule or use the "
                        "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables."
                    ),
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
            except errors.InvalidClientTokenId:
                log.error(
                    "AWS returned an error indicating that the provided credentials are invalid. Somethings to try:"
                    "\n - Ensure that the credentials are correct"
                    "\n - Ensure that the credentials are for the correct AWS account"
                    "\n - Ensure that the credentials have the correct permissions"
                    "\n - Ensure that the credentials are not expired"
                    "\n - Ensure that the credentials are not for a federated user"
                )
                continue

            self.profile_name = profile_name
            break

    def get_boto3_session_for_account(self, account_id: str, region_name: str = None):
        # This need to follow standard credentials provider chain
        if not region_name:
            region_name = self.aws_default_region

        if account_id == self.hub_account_id:
            if not self.profile_name:
                if os.getenv("AWS_ACCESS_KEY_ID"):
                    # environment variables credentials detected
                    self.profile_name = None
                elif profile_name := os.getenv("AWS_PROFILE"):
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
                boto3.Session(profile_name=profile_name, region_name=region_name),
                profile_name,
            )

    async def run_import_aws_resources(self):
        log.info("Importing AWS identities")
        current_command = ctx.command
        ctx.command = Command.IMPORT

        exe_message = ExecutionMessage(
            execution_id=str(uuid.uuid4()),
            command=Command.IMPORT,
            provider_type="aws",
        )
        await import_aws_resources(
            exe_message,
            self.config.aws,
            self.repo_dir,
        )

        ctx.command = current_command

    async def sync_config_aws_accounts(self, accounts: list[AWSAccount]):
        if not (
            len(self.config.aws.accounts)
            > self.config.aws.min_accounts_required_for_wildcard_included_accounts
        ):
            await self.run_import_aws_resources()
            return

        templates = await gather_templates(self.repo_dir, "AWS.*")
        if templates:
            current_command = ctx.command
            ctx.command = Command.CONFIG_DISCOVERY
            log.info(
                "Applying templates to provision identities to the account(s). "
                "This will NOT overwrite any resources that already exist on the account(s). ",
                accounts=[account.account_name for account in accounts],
            )
            exe_message = ExecutionMessage(
                execution_id=str(uuid.uuid4()),
                command=Command.APPLY,
                provider_type="aws",
            )
            sub_config = self.config.aws.copy()
            sub_config.accounts = accounts
            await aws_apply(
                exe_message,
                sub_config,
                load_templates(templates, sub_config.template_map),
            )
            ctx.command = current_command

        await self.run_import_aws_resources()

    async def sync_config_aws_org(self, run_config_discovery: bool = True):
        if not self.config.aws:
            self.config.aws = AWSConfig()

        self.aws_account_map = {}
        current_command = ctx.command

        try:
            if run_config_discovery:
                exe_message = ExecutionMessage(
                    execution_id=str(uuid.uuid4()),
                    command=Command.CONFIG_DISCOVERY,
                )
                await self.config.run_discover_upstream_config_changes(
                    exe_message, self.repo_dir
                )
            await self.config.aws.set_identity_center_details()
        except Exception as err:
            log.info("Failed to refresh AWS accounts", error=err)

        ctx.command = current_command
        self.aws_account_map = {
            account.account_id: account for account in self.config.aws.accounts
        }

    async def run_import_google_workspace_resources(self):
        log.info("Importing Google Workspace identities")
        current_command = ctx.command
        ctx.command = Command.IMPORT

        exe_message = ExecutionMessage(
            execution_id=str(uuid.uuid4()),
            command=Command.IMPORT,
            provider_type="google_workspace",
        )
        await import_google_resources(
            exe_message,
            self.config.google_workspace,
            self.repo_dir,
        )

        ctx.command = current_command

    async def run_import_azure_ad_resources(self):
        log.info("Importing Azure AD identities")
        current_command = ctx.command
        ctx.command = Command.IMPORT

        exe_message = ExecutionMessage(
            execution_id=str(uuid.uuid4()),
            command=Command.IMPORT,
            provider_type="azure_ad",
        )
        await import_azure_ad_resources(
            exe_message,
            self.config.azure_ad,
            self.repo_dir,
        )

        ctx.command = current_command

    async def run_import_okta_resources(self):
        log.info("Importing Okta identities")
        current_command = ctx.command
        ctx.command = Command.IMPORT

        exe_message = ExecutionMessage(
            execution_id=str(uuid.uuid4()),
            command=Command.IMPORT,
            provider_type="okta",
        )
        await import_okta_resources(
            exe_message,
            self.config.okta,
            self.repo_dir,
        )

        ctx.command = current_command

    async def save_and_deploy_changes(self, role_template: AwsIamRoleTemplate):
        log.info(
            "Writing changes locally and deploying updates to AWS",
            role_name=role_template.properties.role_name,
        )

        self.config.write()
        role_template.write(exclude_unset=False)
        await role_template.apply(self.config.aws)

    def configuration_wizard_aws_account_add(self):  # noqa: C901
        if not self.has_confirm_cf_permissions:
            log.info(
                "You have to confirm you have Cloudformation permission in previous question."
            )
            return

        is_hub_account = bool(
            not self.config.aws.accounts and not self.config.aws.organizations
        )
        requires_sync = bool(
            not is_hub_account
            and (
                len(self.config.aws.accounts)
                > self.config.aws.min_accounts_required_for_wildcard_included_accounts
            )
        )
        assume_as_arn = self.assume_as_arn

        if is_hub_account:
            account_id = self.hub_account_id
            account_name = set_required_text_value(
                "What is the name of the AWS Account?"
            )
            default_region = self.aws_default_region
            self.config.aws.spoke_role_is_read_only = set_aws_is_read_only()
            click.echo(
                "\nIAMbic requires Hub and Spoke roles to be created which is deployed using CloudFormation.\n"
                "To review the templates used or deploy them manually, the templates used can be found here:\n"
                "https://github.com/noqdev/iambic/tree/main/iambic/plugins/v0_1_0/aws/cloud_formation/templates\n"
                "If you have already manually deployed the templates, answer yes to proceed.\n"
                "IAMbic will validate that your stacks have been deployed successfully and will not attempt to replace them."
            )

            if not questionary.confirm("Proceed?").unsafe_ask():
                log.info(
                    "Unable to add the AWS Account without creating the required roles."
                )
                return

            role_arn = set_aws_role_arn(account_id)

        else:
            if requires_sync:
                click.echo(
                    "\nAdding this account will require a sync to be run.\n"
                    "This is to apply any matching templates to the account if the resource does not already exist.\n"
                    "Then, the account resources will be imported into Iambic."
                )
                if not questionary.confirm("Proceed?").unsafe_ask():
                    log.info(
                        "Unable to add the AWS account without creating the required role."
                    )
                    return

            account_id = questionary.text(
                "What is the AWS Account ID? Example: `12345689012`"
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

            default_region = set_aws_region(
                "What region should IAMbic use?", self.aws_default_region
            )
            role_arn = set_aws_role_arn(account_id)

            click.echo(
                "\nIAMbic requires Hub and Spoke roles to be created which is deployed using CloudFormation.\n"
                "To review the templates used or deploy them manually, the template used can be found here:\n"
                "https://github.com/noqdev/iambic/blob/main/iambic/plugins/v0_1_0/aws/cloud_formation/templates/IambicSpokeRole.yml\n"
                "If you have already manually deployed the templates, answer yes to proceed.\n"
                "IAMbic will validate that your stacks have been deployed successfully and will not attempt to replace them."
            )

            if not questionary.confirm("Proceed?").unsafe_ask():
                log.info(
                    "Unable to add the AWS account without creating the required role."
                )
                return

        read_only = self.config.aws.spoke_role_is_read_only
        session, profile_name = self.get_boto3_session_for_account(
            account_id, region_name=default_region
        )
        if not session:
            return

        if is_hub_account and not profile_name:
            profile_name = self.profile_name
        elif not is_hub_account:
            profile_name = None

        hub_role_name, spoke_role_name, tags = self.set_aws_cf_customization()

        cf_client = session.client("cloudformation", region_name=default_region)

        if is_hub_account:
            created_successfully = asyncio.run(
                create_iambic_role_stacks(
                    cf_client=cf_client,
                    hub_account_id=account_id,
                    assume_as_arn=assume_as_arn,
                    role_arn=role_arn,
                    read_only=read_only,
                    hub_role_stack_name=hub_role_name,
                    hub_role_name=hub_role_name,
                    spoke_role_stack_name=spoke_role_name,
                    spoke_role_name=spoke_role_name,
                    tags=tags,
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
                    read_only=read_only,
                    hub_role_name=hub_role_name,
                    spoke_role_name=spoke_role_name,
                    tags=tags,
                )
            )
            if not created_successfully:
                log.error(
                    "Failed to create the required IAMbic role. Account not added."
                )
                return

        iambic_managed = (
            IambicManaged.IMPORT_ONLY if read_only else IambicManaged.READ_AND_WRITE
        )
        account = AWSAccount(
            account_id=account_id,
            account_name=account_name,
            spoke_role_arn=get_spoke_role_arn(account_id, role_name=spoke_role_name),
            iambic_managed=iambic_managed,
            aws_profile=profile_name,
            default_region=default_region,
        )
        if is_hub_account:
            account.hub_role_arn = get_hub_role_arn(account_id, role_name=hub_role_name)
        # account.partition = set_aws_account_partition(account.partition)

        confirm_command_exe("AWS Account", Operation.ADDED, requires_sync=requires_sync)

        self.config.aws.accounts.append(account)

        if is_hub_account:
            check_and_update_resource_limit(self.config)
            asyncio.run(self.run_import_aws_resources())
        else:
            self.config.aws = asyncio.run(aws_load(self.config.aws))
            asyncio.run(self.sync_config_aws_accounts([account]))

    def configuration_wizard_aws_account_edit(self):
        account_names = [
            account.account_name
            for account in self.config.aws.accounts
            if not account.org_id
        ]
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
        elif not account_names:
            log.info(
                "No editable accounts found.\n"
                "TIP: An AWS account cannot be edited if it attached to an Organization in the config."
            )
            return
        else:
            account = self.config.aws.accounts[0]

        choices = ["Go back", "Update region"]
        if not account.org_id:
            choices.append("Update name")

        while True:
            action = questionary.select(
                "What would you like to do?",
                choices=choices,
            ).unsafe_ask()
            if action == "Go back":
                return
            elif action == "Update region":
                account.default_region = set_aws_region(
                    "What region should IAMbic use?", account.default_region
                )
            elif action == "Update name":
                account.account_name = questionary.text(
                    "What is the name of the AWS Account?",
                    default=account.account_name,
                ).unsafe_ask()

            confirm_command_exe("AWS Account", Operation.UPDATED)

            self.config.aws.accounts[
                account_id_to_config_elem_map[account.account_id]
            ] = account
            asyncio.run(self.run_import_aws_resources())
            self.config.write()

    def setup_aws_configuration(self):
        if self.has_aws_account_or_organizations:
            self.hub_account_id = self.config.aws.hub_role_arn.split(":")[4]
            self.spoke_role_is_read_only = self.config.aws.spoke_role_is_read_only
        else:
            self.hub_account_id = None

        try:
            if getattr(self, "boto3_session", None) is None:
                # need bootstrapping
                self.boto3_session = boto3.Session(region_name=self.aws_default_region)
                self.autodetected_org_settings = {}
                try:
                    org_client = self.boto3_session.client("organizations")
                    self.autodetected_org_settings = org_client.describe_organization()[
                        "Organization"
                    ]
                except Exception:
                    # we are wrapping inside a try-except block because the user
                    # may not have organization setup yet, so we don't want to
                    # crash in that case.
                    pass

            default_caller_identity = self.boto3_session.client(
                "sts", region_name=self.aws_default_region
            ).get_caller_identity()
            caller_arn = get_identity_arn(default_caller_identity)
            default_hub_account_id = caller_arn.split(":")[4]
        except (
            AttributeError,
            IndexError,
            NoCredentialsError,
            ClientError,
            FileNotFoundError,
        ):
            default_hub_account_id = None
            default_caller_identity = {}

        if not self.hub_account_id:
            while True:
                click.echo(
                    "\nTo get started with the IAMbic setup wizard, you'll need an AWS account.\n"
                    "This is where IAMbic will deploy its main role.\n"
                    "If you have an AWS Organization, that account will be your hub account.\n"
                    "Review to-be-created IAMbic roles at\n"
                    "https://docs.iambic.org/reference/aws_hub_and_spoke_roles"
                )
                self.hub_account_id = set_required_text_value(
                    "Which Account ID should we use to deploy the IAMbic hub role?",
                    default_val=default_hub_account_id,
                )
                if is_valid_account_id(self.hub_account_id):
                    break

        if self.hub_account_id == default_hub_account_id:
            identity_arn = get_identity_arn(default_caller_identity)
            click.echo(
                f"\nIAMbic detected you are using {identity_arn} for AWS access.\n"
                f"This identity will require the ability to create "
                f"CloudFormation stacks, stack sets, and stack set instances."
            )
            if questionary.confirm("Would you like to use this identity?").ask():
                # If we are going to use the default_caller_identity,
                # we need to set teh autodetected_org_settings to
                self.caller_identity = default_caller_identity
            else:
                self.set_boto3_session()
        else:
            self.set_boto3_session()

        asyncio.run(self.sync_config_aws_org())

    def configuration_wizard_aws_accounts(self):
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
            "Update IdentityCenter Region",
            "Update IAMbic control",
            "Update Region",
        ]
        while True:
            action = questionary.select(
                "What would you like to do?",
                choices=choices,
            ).unsafe_ask()
            if action == "Go back":
                return
            elif action == "Update Region":
                org_to_edit.default_region = set_aws_region(
                    "What region should IAMbic use?", org_to_edit.default_region
                )
            elif action == "Update IdentityCenter Region":
                org_to_edit.identity_center = set_identity_center()
                asyncio.run(self.sync_config_aws_org(False))

            confirm_command_exe("AWS Organization", Operation.UPDATED)
            self.config.aws.organizations[
                org_id_to_config_elem_map[org_to_edit.org_id]
            ] = org_to_edit
            self.config.write()

    def configuration_wizard_aws_organizations_add(self):
        # we reset the previous known states since the user chose
        # enter this flow again, so we will re-query the cloud control plane.
        self._reset_cf_stacksets_known_states()  # address https://github.com/noqdev/iambic/issues/574
        if not self.has_cf_stacksets_permissions:
            log.info(
                "Unable to edit this attribute without CloudFormation permissions."
            )
            return

        org_console_url = f"https://{self.aws_default_region}.console.aws.amazon.com/organizations/v2/home/accounts"
        click.echo(
            f"\nWhat is the AWS Organization ID?\nIt can be found here {org_console_url}"
        )
        org_id = questionary.text(
            "AWS Organization ID: ",
            default=self.autodetected_org_settings.get("Id", ""),
        ).unsafe_ask()
        account_id = self.hub_account_id
        session, profile_name = self.get_boto3_session_for_account(account_id)
        if not session:
            return

        read_only = set_aws_is_read_only()
        self.config.aws.spoke_role_is_read_only = read_only
        assume_as_arn = self.assume_as_arn
        cf_role_arn = self.cf_role_arn

        click.echo(
            "\nIAMbic requires Hub and Spoke roles to be created which is deployed using CloudFormation.\n"
            "To review the templates used or deploy them manually, the templates used can be found here:\n"
            "https://github.com/noqdev/iambic/tree/main/iambic/plugins/v0_1_0/aws/cloud_formation/templates\n"
            "If you have already manually deployed the templates, answer yes to proceed.\n"
            "IAMbic will validate that your stacks have been deployed successfully and will not attempt to replace them."
        )
        if not questionary.confirm("Proceed?").unsafe_ask():
            log.info("Unable to add the AWS Org without creating the required roles.")
            return

        hub_role_name, spoke_role_name, tags = self.set_aws_cf_customization()

        created_successfully = asyncio.run(
            create_iambic_role_stacks(
                cf_client=session.client(
                    "cloudformation", region_name=self.aws_default_region
                ),
                hub_account_id=account_id,
                assume_as_arn=assume_as_arn,
                role_arn=cf_role_arn,
                org_client=session.client(
                    "organizations", region_name=self.aws_default_region
                ),
                read_only=read_only,
                hub_role_stack_name=hub_role_name,
                hub_role_name=hub_role_name,
                spoke_role_stack_name=spoke_role_name,
                spoke_role_name=spoke_role_name,
                tags=tags,
            )
        )
        if not created_successfully:
            log.error("Failed to create the required IAMbic roles. Exiting.")
            sys.exit(0)

        aws_org = AWSOrganization(
            org_id=org_id,
            org_account_id=account_id,
            default_rule=BaseAWSOrgRule(),
            hub_role_arn=get_hub_role_arn(account_id, role_name=hub_role_name),
            aws_profile=profile_name,
            spoke_role_is_read_only=read_only,
            default_region=self.aws_default_region,
            preferred_spoke_role_name=spoke_role_name,
        )
        if self.config.aws.spoke_role_is_read_only:
            aws_org.default_rule.iambic_managed = IambicManaged.IMPORT_ONLY
        else:
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
            click.echo(
                "\nThe AWS Org will not be added to the config and wizard will exit."
            )
            if questionary.confirm("Proceed?").unsafe_ask():
                log.info("Exiting...")
                sys.exit(0)

        log.info("Saving config.")
        self.config.write()

        if not questionary.confirm(
            "Add the org accounts to the config and import the org's AWS identities?"
        ).unsafe_ask():
            click.echo(
                "\nThis is required to finish the setup process.\nWizard will exit if this has not been setup."
            )
            if questionary.confirm("Exit?").unsafe_ask():
                log.info("Exiting...")
                sys.exit(0)

        asyncio.run(self.sync_config_aws_org())

    def configuration_wizard_aws_organizations(self):
        def maybe_prompt():
            if (
                self.autodetected_org_settings
                and self.hub_account_id
                == self.autodetected_org_settings["MasterAccountId"]
            ):
                # https://github.com/noqdev/iambic/issues/405
                # no need to prompt because we succeed in detecting organization and hub_account_id matches the org management account
                return True
            else:
                # Currently only 1 org per config is supported.
                log.error(
                    "If you would like to use AWS Organizations, the IAMbic hub account you"
                    "\nconfigured must be the same AWS account as your AWS Organization."
                    "\nPlease follow AWS guide to setup an AWS organization first. If you already have an organization setup,"
                    "\nmake sure you are using the organization management account before running IAMbic setup"
                )
                raise ValueError("Not AWS Organization management account")

        try:
            if maybe_prompt():
                if self.config.aws and self.config.aws.organizations:
                    self.configuration_wizard_aws_organizations_edit()
                else:
                    self.configuration_wizard_aws_organizations_add()
        except ValueError as e:
            if e.args[0] == "Not AWS Organization management account":
                return
            else:
                raise

    def configuration_wizard_aws(self):
        self.setup_aws_configuration()
        click.echo(
            "\nWe recommend configuring IAMbic with AWS Organizations, "
            "but you may also manually configure accounts."
        )
        while True:
            action = questionary.select(
                "What would you like to configure in AWS?",
                choices=["Go back", "AWS Organizations", "AWS Accounts"],
            ).unsafe_ask()
            if action == "Go back":
                return
            elif action == "AWS Organizations":
                self.configuration_wizard_aws_organizations()
            elif action == "AWS Accounts":
                self.configuration_wizard_aws_accounts()

    def upsert_secret(self):
        if not self.config.secrets:
            self.config.secrets = {}

        if self.config.okta:
            self.config.secrets["okta"] = get_secret_dict_with_val(
                self.config.okta,
                exclude={"organizations": {"__all__": {"client"}}},
                exclude_unset=True,
            )

        if self.config.azure_ad:
            self.config.secrets["azure_ad"] = get_secret_dict_with_val(
                self.config.azure_ad, exclude_unset=True
            )

        if self.config.google_workspace:
            self.config.secrets["google_workspace"] = get_secret_dict_with_val(
                self.config.google_workspace,
                exclude={"_service_connection_map"},
                exclude_unset=True,
            )

        if len(self.config.extends) == 0:
            self.create_secret()
        else:
            self.update_secret()

    def create_secret(self):
        response = None

        if len(self.config.extends) == 0:
            if self.aws_account_map:
                response = questionary.select(
                    "Where do you want to store your secrets?",
                    choices=[
                        LOCALLY,
                        AWS_SECRETS,
                    ],
                ).ask()
            else:
                # TODO: ask if they want to create the file
                response = LOCALLY
        elif self.config.extends[0].key == ExtendsConfigKey.AWS_SECRETS_MANAGER:
            response = AWS_SECRETS
        elif self.config.extends[0].key == ExtendsConfigKey.LOCAL_FILE:
            response = LOCALLY

        if response == AWS_SECRETS:
            region = set_aws_region(
                "What region should the secret be created in?",
                self.aws_default_region,
            )

            question_text = "Create the secret"
            role_name = IAMBIC_SPOKE_ROLE_NAME
            role_account_id = self.hub_account_id

            if not questionary.confirm(f"{question_text}?").unsafe_ask():
                self.config.secrets = {}
                return

            if role_name and (aws_account := self.aws_account_map.get(role_account_id)):
                session = asyncio.run(aws_account.get_boto3_session(region_name=region))
            else:
                session = boto3.Session(region_name=region)

            client = session.client(service_name="secretsmanager", region_name=region)
            response = client.create_secret(
                Name=f"iambic-config-secrets-{str(uuid.uuid4())}",
                Description="IAMbic managed secret used to store protected config values",
                SecretString=yaml.dump({"secrets": self.config.secrets}),
            )

            self.config.extends = [
                ExtendsConfig(
                    key=ExtendsConfigKey.AWS_SECRETS_MANAGER,
                    value=response["ARN"],
                    assume_role_arn=get_spoke_role_arn(self.hub_account_id),
                )  # type: ignore
            ]
            self.config.write()
        elif response == LOCALLY:
            # TODO: add check to gitignore the file
            with open(self.secret_config_dir(), "w") as f:
                f.write(yaml.dump({"secrets": self.config.secrets}))  # type: ignore

            self.config.extends = [
                ExtendsConfig(
                    key=ExtendsConfigKey.LOCAL_FILE,
                    value="secrets.yaml",
                )  # type: ignore
            ]

            self.config.write()

    def update_secret(self):
        response = None

        if self.config.extends[0].key == ExtendsConfigKey.AWS_SECRETS_MANAGER:
            response = AWS_SECRETS
        elif self.config.extends[0].key == ExtendsConfigKey.LOCAL_FILE:
            response = LOCALLY

        secret_details = self.config.extends[0]

        if response == AWS_SECRETS:
            secret_arn = secret_details.value
            region = secret_arn.split(":")[3]
            secret_account_id = secret_arn.split(":")[4]

            if aws_account := self.aws_account_map.get(secret_account_id):
                session = asyncio.run(aws_account.get_boto3_session(region_name=region))
            else:
                session = boto3.Session(region_name=region)

            client = session.client(service_name="secretsmanager", region_name=region)
            client.put_secret_value(
                SecretId=secret_arn,
                SecretString=yaml.dump({"secrets": self.config.secrets}),
            )
        elif response == LOCALLY:
            secrets_config_path = self.secret_config_dir(secret_details.value)
            with open(secrets_config_path, "w") as f:
                f.write(yaml.dump({"secrets": self.config.secrets}))  # type: ignore

            self.config.write()

    def configuration_wizard_google_workspace_add(self):
        google_obj = {
            "subjects": [set_google_subject()],
            "type": set_google_project_type(),
            "project_id": set_google_project_id(),
            "private_key_id": set_google_private_key_id(),
            "private_key": set_google_private_key(),
            "client_email": set_google_client_email(),
            "client_id": set_client_id(),
            "auth_uri": set_google_auth_uri(),
            "token_uri": set_google_token_uri(),
            "auth_provider_x509_cert_url": set_google_auth_provider_cert_url(),
            "client_x509_cert_url": set_google_client_cert_url(),
        }

        confirm_command_exe("Google Workspace", Operation.ADDED)

        project = GoogleProject(**google_obj)

        if self.config.secrets and self.config.google_workspace:
            self.config.google_workspace.workspaces.append(project)
        else:
            self.config.google_workspace = GoogleWorkspaceConfig(workspaces=[project])

        asyncio.run(self.run_import_google_workspace_resources())
        self.upsert_secret()

    def configuration_wizard_google_workspace_edit(self):
        project_ids = [
            project.project_id for project in self.config.google_workspace.workspaces
        ]
        project_id_to_config_elem_map = {
            project.project_id: elem
            for elem, project in enumerate(self.config.google_workspace.workspaces)
        }
        if len(project_ids) > 1:
            action = questionary.select(
                "Which Google Workspace would you like to edit?",
                choices=["Go back", *project_ids],
            ).unsafe_ask()
            if action == "Go back":
                return
            project_to_edit = next(
                (
                    project
                    for project in self.config.google_workspace.workspaces
                    if project.project_id == action
                ),
                None,
            )
            if not project_to_edit:
                log.debug("Could not find AWS Organization to edit", org_id=action)
                return
        else:
            project_to_edit = self.config.google_workspace.workspaces[0]

        project_id = project_to_edit.project_id
        choices = [
            "Go back",
            "Update Subject",
            "Update Type",
            "Update Private Key",
            "Update Private Key ID",
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
                    GoogleSubject(**set_google_subject(default_domain, default_service))
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
                project_to_edit.client_id = set_client_id(project_to_edit.client_id)
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

            confirm_command_exe("Google Workspace", Operation.UPDATED)

            self.config.google_workspace.workspaces[
                project_id_to_config_elem_map[project_id]
            ] = project_to_edit

            asyncio.run(self.run_import_google_workspace_resources())
            self.upsert_secret()
            self.config.write()

    def configuration_wizard_google_workspace(self):
        log.info(
            "For details on how to retrieve the information required to add a Google Workspace "
            "to IAMbic check out our docs: https://docs.iambic.org/getting_started/google/"
        )

        if self.config.google_workspace:
            action = questionary.select(
                "What would you like to do?",
                choices=["Go back", "Add", "Edit"],
            ).unsafe_ask()
            if action == "Go back":
                return
            elif action == "Add":
                self.configuration_wizard_google_workspace_add()
            elif action == "Edit":
                self.configuration_wizard_google_workspace_edit()
        else:
            self.configuration_wizard_google_workspace_add()

    def configuration_wizard_okta_organization_add(self):
        okta_obj = {
            "idp_name": set_idp_name(),
            "org_url": set_okta_org_url(),
            "api_token": set_okta_api_token(),
        }

        confirm_command_exe("Okta Organization", Operation.ADDED)

        organization = OktaOrganization(**okta_obj)

        if self.config.secrets and self.has_okta_configured:
            self.config.okta.organizations.append(organization)
        else:
            self.config.okta = OktaConfig(organizations=[organization])

        asyncio.run(self.run_import_okta_resources())
        self.upsert_secret()

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
                org_to_edit.idp_name = set_idp_name(org_to_edit.idp_name)
            elif action == "Update Organization URL":
                org_to_edit.org_url = set_okta_org_url(org_to_edit.org_url)
            elif action == "Update API Token":
                org_to_edit.api_token = set_okta_api_token(org_to_edit.api_token)

            confirm_command_exe("Okta Organization", Operation.UPDATED)
            self.config.okta.organizations[
                org_name_to_config_elem_map[org_name]
            ] = org_to_edit

            asyncio.run(self.run_import_okta_resources())
            self.upsert_secret()
            self.config.write()

    def configuration_wizard_okta(self):
        log.info(
            "For details on how to retrieve the information required to add an Okta Organization "
            "to IAMbic check out our docs: https://docs.iambic.org/getting_started/okta/"
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

    def configuration_wizard_azure_ad_organization_add(self):
        azure_ad_obj = {
            "idp_name": set_idp_name(),
            "tenant_id": set_tenant_id(),
            "client_id": set_client_id(),
            "client_secret": set_client_secret(),
        }

        confirm_command_exe("Azure AD Organization", Operation.ADDED)

        organization = AzureADOrganization(**azure_ad_obj)

        if (
            self.config.secrets
            and self.config.azure_ad
            and self.config.azure_ad.organizations
        ):
            self.config.azure_ad.organizations.append(organization)
        else:
            self.config.azure_ad = AzureADConfig(organizations=[organization])

        asyncio.run(self.run_import_azure_ad_resources())
        self.upsert_secret()

    def configuration_wizard_azure_ad_organization_edit(self):
        org_names = [org.idp_name for org in self.config.azure_ad.organizations]
        org_name_to_config_elem_map = {
            org.idp_name: elem
            for elem, org in enumerate(self.config.azure_ad.organizations)
        }
        if len(org_names) > 1:
            action = questionary.select(
                "Which Azure AD Organization would you like to edit?",
                choices=["Go back", *org_names],
            ).unsafe_ask()
            if action == "Go back":
                return
            org_to_edit = next(
                (
                    org
                    for org in self.config.azure_ad.organizations
                    if org.idp_name == action
                ),
                None,
            )
            if not org_to_edit:
                log.debug(
                    "Could not find Azure AD Organization to edit", idp_name=action
                )
                return
        else:
            org_to_edit = self.config.azure_ad.organizations[0]

        org_name = org_to_edit.idp_name
        choices = [
            "Go back",
            "Update IDP name",
            "Update Tenant ID",
            "Update Client ID",
            "Update Client Secret",
        ]
        while True:
            action = questionary.select(
                "What would you like to do?",
                choices=choices,
            ).unsafe_ask()
            if action == "Go back":
                return
            elif action == "Update IDP name":
                org_to_edit.idp_name = set_idp_name(org_to_edit.idp_name)
            elif action == "Update Tenant ID":
                org_to_edit.tenant_id = set_tenant_id(org_to_edit.tenant_id)
            elif action == "Update Client ID":
                org_to_edit.client_id = set_client_id(org_to_edit.client_id)
            elif action == "Update Client Secret":
                org_to_edit.client_secret = set_client_secret()

            confirm_command_exe("Azure AD Organization", Operation.UPDATED)
            self.config.azure_ad.organizations[
                org_name_to_config_elem_map[org_name]
            ] = org_to_edit

            asyncio.run(self.run_import_azure_ad_resources())

            self.upsert_secret()
            self.config.write()

    def configuration_wizard_azure_ad(self):
        log.info(
            "For details on how to retrieve the information required to add an Azure AD Organization "
            "to IAMbic check out our docs: https://docs.iambic.org/getting_started/azure_ad/"
        )
        if self.config.azure_ad:
            action = questionary.select(
                "What would you like to do?",
                choices=["Go back", "Add", "Edit"],
            ).unsafe_ask()
            if action == "Go back":
                return
            elif action == "Add":
                self.configuration_wizard_azure_ad_organization_add()
            elif action == "Edit":
                self.configuration_wizard_azure_ad_organization_edit()
        else:
            self.configuration_wizard_azure_ad_organization_add()

    def set_aws_cf_customization(self):
        hub_role_name = IAMBIC_HUB_ROLE_NAME
        spoke_role_name = IAMBIC_SPOKE_ROLE_NAME
        if self._is_more_options:
            input_hub_role_name = questionary.text(
                "(Optional) Iambic Hub Role Name: ",
                default="",
            ).unsafe_ask()
            input_spoke_role_name = questionary.text(
                "(Optional) Iambic Spoke Role Name: ",
                default="",
            ).unsafe_ask()
            if input_hub_role_name:
                hub_role_name = input_hub_role_name
            if input_spoke_role_name:
                spoke_role_name = input_spoke_role_name
        unparse_tags = questionary.text(
            "Add Tags (leave blank or `team=ops_team, cost_center=engineering`): ",
            default="",
            validate=validate_aws_cf_input_tags,
        ).ask()
        tags = aws_cf_parse_key_value_string(unparse_tags)
        return hub_role_name, spoke_role_name, tags

    def configuration_github_app_aws_lambda_setup(self):  # noqa: C901
        from iambic.plugins.v0_1_0.aws.cloud_formation.utils import (
            IAMBIC_GITHUB_APP_SUFFIX,
        )
        from iambic.plugins.v0_1_0.github.create_github_app import (
            get_github_app_secrets,
            has_github_app_secrets_locally,
            remove_github_app_secrets,
        )
        from iambic.plugins.v0_1_0.github.manage_github_app import (
            generate_jwt,
            update_webhook_url,
            verify_access,
        )

        if has_github_app_secrets_locally():
            existing_secrets = get_github_app_secrets()
            owner = existing_secrets.get("owner", {}).get("login", "UNKNOWN")
            app_name = existing_secrets.get("name", "UNKNOWN_APP_NAME")
            if not questionary.confirm(
                f"We found existing GitHub app secrets for owner: {owner} as app: {app_name}.\n"
                "Do you want us to use it to setup IAMbic GitHub integration"
            ).unsafe_ask():
                log.error(
                    "Please remove ~/.iambic/.github_secrets.yaml before re-running this wizard"
                )
                return

        github_app_secrets = get_github_app_secrets()

        assert github_app_secrets

        github_app_url = github_app_secrets.get("html_url", "")

        log.info(
            "We are attempting to open a browser window to the GitHub App installation page.\n"
            "Please install the app and grant it access to your `iambic-templates` and `iambic-templates-gist` repositories.\n"
            "If your browser doesn't open, please visit the following URL manually to install the GitHub app and grant access.\n"
            f"{github_app_url}\n"
            "Proceed once this is complete.\n\n"
        )
        webbrowser.open(github_app_url, new=0, autoraise=True)
        if not questionary.confirm("Proceed?").unsafe_ask():
            return

        # verify github app control plane access
        github_app_jwt = generate_jwt(github_app_secrets)
        if not verify_access(github_app_jwt):
            log.error("We were unable to verify access to Github. Aborting.")
            return

        github_app_installations = get_github_app_installations(github_app_jwt)
        if not github_app_installations:
            log.error("Unable to find Github app installations. Aborting.")
            return

        if len(github_app_installations) > 1:
            log.error(
                "We found more than one Github app installation. It should only be installed in one Github Organization. Aborting."
            )
            return

        iambic_github_installation_id = github_app_installations[0]["id"]

        github_app_installation_repos = get_repos_for_installation(
            github_app_jwt, iambic_github_installation_id
        )

        iambic_templates_repo = next(
            (
                r
                for r in github_app_installation_repos
                if "iambic-templates" in r["name"] and "-gist" not in r["name"]
            ),
            None,
        )
        iambic_templates_gist_repo = next(
            (
                r
                for r in github_app_installation_repos
                if "iambic-templates-gist" in r["name"]
            ),
            None,
        )
        github_app_secrets.update(
            {
                "iambic_templates_repo_url": iambic_templates_repo["clone_url"],
                "iambic_templates_gist_repo_url": iambic_templates_gist_repo[
                    "clone_url"
                ],
                "iambic_templates_repo_full_name": iambic_templates_repo["full_name"],
                "iambic_templates_gist_repo_full_name": iambic_templates_gist_repo[
                    "full_name"
                ],
                "iambic_github_installation_id": iambic_github_installation_id,
            }
        )
        # save secret for pem and webhook_url

        click.echo(
            "\nSetting up a GitHub App for IAMbic involves creating CloudFormation stacks. \n"
            "If you wish to inspect the templates used or handle their deployment manually, use the `iambic_github_app` templates at the following location:\n"
            "https://github.com/noqdev/iambic/tree/main/iambic/plugins/v0_1_0/aws/cloud_formation/templates\n"
            "Note that IAMbic will verify the successful deployment of your stacks, and it will not attempt to overwrite or recreate them if they already exist.\n"
        )

        unparse_tags = questionary.text(
            "Add Tags (leave blank or `team=ops_team, cost_center=engineering`): ",
            default="",
            validate=validate_aws_cf_input_tags,
        ).ask()
        tags = aws_cf_parse_key_value_string(unparse_tags)
        if not questionary.confirm("Proceed?").unsafe_ask():
            return

        account_name_to_account_id = {
            account.account_name: account.account_id
            for account in self.config.aws.accounts
        }
        available_account_names = sorted(list(account_name_to_account_id.keys()))
        questionary_params = {}
        question_text = "We recommend you deploy Lambda integration on a non-management account.\nTarget AWS Account name: "
        if len(available_account_names) == 1:
            target_account_name = available_account_names[0]
        elif len(available_account_names) < 10:
            target_account_name = questionary.select(
                question_text, choices=available_account_names, **questionary_params
            ).unsafe_ask()
        else:
            target_account_name = questionary.autocomplete(
                question_text,
                choices=available_account_names,
                style=CUSTOM_AUTO_COMPLETE_STYLE,
                **questionary_params,
            ).unsafe_ask()

        target_account_id = account_name_to_account_id[target_account_name]
        log.info(f"Target AWS Account ID is {target_account_id}")

        session, _ = self.get_boto3_session_for_account(target_account_id)

        # TODO migration notes since we are using a new secrets format
        secretsmanager_client = session.client(
            service_name="secretsmanager", region_name=self.aws_default_region
        )
        secrets_kwargs = {}
        if tags:
            secrets_kwargs["Tags"] = tags
        try:
            response = secretsmanager_client.create_secret(
                Name="iambic/github-app-secrets",
                Description="iambic github app private key",
                SecretString=yaml.dump(github_app_secrets),
                **secrets_kwargs,
            )
        except secretsmanager_client.exceptions.ResourceExistsException:
            log.info(
                f"iambic/github-app-secrets already exists in account: {target_account_id} in region: {self.aws_default_region}"
            )

            needs_to_prompt_user_to_update_secret = True
            # verify the existing secrets actually match our known values
            response = secretsmanager_client.get_secret_value(
                SecretId="iambic/github-app-secrets",
            )
            if "SecretString" in response:
                cloud_secrets = yaml.load(response["SecretString"])
                if (
                    cloud_secrets.get("pem", None)
                    == github_app_secrets.get("pem", None)
                ) and (
                    cloud_secrets.get("webhook_secret", None)
                    == github_app_secrets.get("webhook_secret", None)
                ):
                    needs_to_prompt_user_to_update_secret = False

            if (
                needs_to_prompt_user_to_update_secret
                and not questionary.confirm(
                    "Continue with value in existing Secret?"
                ).unsafe_ask()
            ):
                log.error(
                    "Please remove the iambic/github-app-secrets secret or update the secret before re-running this wizard"
                )
                return

        cf_client = session.client(
            "cloudformation", region_name=self.aws_default_region
        )

        # Note: We are not going to prompt user to give us an optional CloudFormation Role ARN
        # to use because it seems like additional friction. If we get feedback to restore it,
        # we will simply called cf_role_arn = self.cf_role_arn
        cf_role_arn = None

        successfully_created = asyncio.run(
            create_github_app_roles_stack(
                cf_client,
                self.hub_account_id,
                IAMBIC_HUB_ROLE_NAME,
                cf_role_arn,
                tags=tags,
            )
        )
        assert successfully_created

        # modify the trust policy of IambicHubRole to allow iambic lambda execution role
        lambda_role_arn = f"arn:aws:iam::{target_account_id}:role/iambic_github_app_lambda_execution{IAMBIC_GITHUB_APP_SUFFIX}"

        self.github_app_amend_trust_policy_for_iambic_integration(lambda_role_arn)

        successfully_created = asyncio.run(
            create_github_app_ecr_pull_through_cache_stack(
                cf_client,
                cf_role_arn,
                tags=tags,
            )
        )
        assert successfully_created

        successfully_created = asyncio.run(
            create_github_app_ecr_repo_stack(
                cf_client,
                cf_role_arn,
                tags=tags,
            )
        )
        assert successfully_created

        successfully_created = asyncio.run(
            create_github_app_code_build_stack(
                cf_client,
                target_account_id,
                cf_role_arn,
                tags=tags,
            )
        )
        assert successfully_created

        self.github_app_pull_latest_iambic_image(session)

        self.github_app_wait_until_image_is_ready(session)

        successfully_created = asyncio.run(
            create_github_app_lambda_stack(
                cf_client,
                target_account_id,
                cf_role_arn,
                tags=tags,
            )
        )
        assert successfully_created

        webhook_url = None

        lambda_stack_name = f"IAMbicGitHubAppLambda{IAMBIC_GITHUB_APP_SUFFIX}"
        response = cf_client.describe_stacks(StackName=lambda_stack_name)
        outputs = response["Stacks"][0]["Outputs"]
        for output in outputs:
            keyName = output["OutputKey"]
            if keyName == "FunctionUrl":
                webhook_url = output["OutputValue"]

        assert webhook_url

        github_app_jwt = generate_jwt(github_app_secrets)
        try:
            update_webhook_url(webhook_url, github_app_jwt)
        except Exception:
            log.exception(
                "Failed to update webhook URL with GitHub App. Please manually update the webhook URL in the GitHub App settings page",
                webhook_url=webhook_url,
            )
            if not questionary.confirm("Proceed?").unsafe_ask():
                return

        # Remove the local secrets because it's already saved in secret manager
        remove_github_app_secrets()

    def github_app_amend_trust_policy_for_iambic_integration(self, lambda_role_arn):
        hub_session, _ = self.get_boto3_session_for_account(self.hub_account_id)
        hub_iam_client = hub_session.client("iam", region_name=self.aws_default_region)
        hub_role_arn = self.config.aws.hub_role_arn
        hub_role_name = hub_role_arn.split("/")[-1]
        resp = hub_iam_client.get_role(RoleName=hub_role_name)
        existing_trust_policy = resp["Role"]["AssumeRolePolicyDocument"]
        trust_lambda_execution_role = False
        needs_to_add_statement = True
        statements: list = existing_trust_policy.get("Statement", [])
        new_statement = {
            "Sid": "AllowIAMbicLambdaIntegration",
            "Effect": "Allow",
            "Principal": {"AWS": lambda_role_arn},
            "Action": ["sts:AssumeRole", "sts:TagSession"],
        }
        for statement in statements:  # FIXME: watch out other cases
            if statement.get("Sid", "") == "AllowIAMbicLambdaIntegration":
                needs_to_add_statement = False
                if statement["Principal"]["AWS"] != lambda_role_arn:
                    # Update the statement
                    statement["Principal"]["AWS"] = lambda_role_arn
                else:
                    trust_lambda_execution_role = True
        if needs_to_add_statement:
            statements.append(new_statement)
        if not trust_lambda_execution_role:
            try:
                resp = hub_iam_client.update_assume_role_policy(
                    RoleName=hub_role_name,
                    PolicyDocument=json.dumps(existing_trust_policy),
                )
                log.info(f"Added trust policy on {hub_role_arn} for {lambda_role_arn}")
            except Exception as e:
                log.error(e)

    def github_app_pull_latest_iambic_image(self, session):
        # FIXME shortcircuit if build image is already present
        # FIXME but then how to deal with version upgrade
        code_build_client = session.client(
            "codebuild", region_name=self.aws_default_region
        )

        try:
            response = code_build_client.start_build(
                projectName="iambic_code_build",
            )
        except errors.ResourceNotFoundException:
            log.exception(
                "CodeBuild project not found. Please inspect the CloudFormation stacks in your AWS account to determine the cause of the failure"
            )
            raise

        build_id = response["build"]["id"]
        # FIXME explain why this is stalling for builds
        log.info("Preparing container image. This process should take around 2 minutes")
        for _ in range(6):
            resp = code_build_client.batch_get_builds(ids=[build_id])
            build_status = resp["builds"][0]["buildStatus"]
            if build_status == "IN_PROGRESS":
                time.sleep(30)
                continue
            elif build_status == "SUCCEEDED":
                break
            else:
                raise ValueError(f"build status is {build_status}")

    def github_app_wait_until_image_is_ready(self, session):
        repository_name = "iambic-ecr-public/iambic/iambic"
        ecr_client = session.client("ecr", region_name=self.aws_default_region)
        for _ in range(6):
            try:
                resp = ecr_client.describe_images(
                    repositoryName=repository_name, imageIds=[{"imageTag": "latest"}]
                )
                if len(resp["imageDetails"]) == 0:
                    time.sleep(30)
                    continue
                else:
                    break
            except ecr_client.exceptions.ImageNotFoundException:
                time.sleep(30)
                continue

    def configuration_wizard_change_detection_setup(self, aws_org: AWSOrganization):
        click.echo(
            "\nTo setup change detection for iambic it requires creating CloudFormation stacks "
            "and a CloudFormation stack set.\n"
            "To review the templates used or deploy them manually, the IdentityRule templates used can be found here:\n"
            "https://github.com/noqdev/iambic/tree/main/iambic/plugins/v0_1_0/aws/cloud_formation/templates\n"
            "If you have already manually deployed the templates, answer yes to proceed.\n"
            "IAMbic will validate that your stacks have been deployed successfully and will not attempt to replace them."
        )
        unparse_tags = questionary.text(
            "Add Tags (leave blank or `team=ops_team, cost_center=engineering`): ",
            default="",
            validate=validate_aws_cf_input_tags,
        ).ask()
        tags = aws_cf_parse_key_value_string(unparse_tags)
        if not questionary.confirm("Proceed?").unsafe_ask():
            return

        session, _ = self.get_boto3_session_for_account(aws_org.org_account_id)
        # cloudtrail is not cross-region, so we need to use us-east-1
        cf_client = session.client(
            "cloudformation", region_name="us-east-1"  # self.aws_default_region
        )
        org_client = session.client(
            "organizations", region_name=self.aws_default_region
        )

        successfully_created = asyncio.run(
            create_iambic_eventbridge_stacks(
                cf_client,
                org_client,
                aws_org.org_id,
                aws_org.org_account_id,
                self.cf_role_arn,
                tags=tags,
            )
        )
        if not successfully_created:
            return

        role_name = IAMBIC_SPOKE_ROLE_NAME
        hub_account_id = self.hub_account_id
        # cloudtrail is not cross-region, so we need to use us-east-1
        # sqs_arn = f"arn:aws:sqs:{self.aws_default_region}:{hub_account_id}:IAMbicChangeDetectionQueue{IAMBIC_CHANGE_DETECTION_SUFFIX}"
        sqs_arn = f"arn:aws:sqs:us-east-1:{hub_account_id}:IAMbicChangeDetectionQueue{IAMBIC_CHANGE_DETECTION_SUFFIX}"

        if not self.existing_role_template_map:
            log.info("Loading AWS role templates...")
            self.existing_role_template_map = asyncio.run(
                get_existing_template_map(
                    self.repo_dir, AWS_IAM_ROLE_TEMPLATE_TYPE, self.config.template_map
                )
            )

        role_template: AwsIamRoleTemplate = self.existing_role_template_map.get(
            role_name
        )

        self.config.aws.sqs_cloudtrail_changes_queues = [sqs_arn]
        asyncio.run(self.save_and_deploy_changes(role_template))

    def run(self):  # noqa: C901
        """Run the configuration wizard.

        This will prompt the user for the required information to configure IAMbic.

        Notes:
        - AWS is not required to use IAMbic, but it is required to store to aws secrets.
        """

        while True:
            choices = []
            secret_question_text, _ = self.secrets_message

            if "aws" in self.config.__fields__:
                choices.append("AWS")
            if "azure_ad" in self.config.__fields__:
                choices.append("Azure AD")
            if "google_workspace" in self.config.__fields__:
                choices.append("Google Workspace")
            if "okta" in self.config.__fields__:
                choices.append("Okta")

            if self.has_aws_account_or_organizations:
                choices.append("Setup GitHub App Integration using AWS Lambda")
                if (
                    self.config.aws.organizations
                    and not self.config.aws.sqs_cloudtrail_changes_queues
                ):
                    choices.append("Setup AWS change detection")

            choices.append("Done")

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
                elif action == "Google Workspace":
                    if questionary.confirm(
                        f"{secret_question_text} Proceed?"
                    ).unsafe_ask():
                        self.configuration_wizard_google_workspace()
                elif action == "Okta":
                    if questionary.confirm(
                        f"{secret_question_text} Proceed?"
                    ).unsafe_ask():
                        self.configuration_wizard_okta()
                elif action == "Azure AD":
                    if questionary.confirm(
                        f"{secret_question_text} Proceed?"
                    ).unsafe_ask():
                        self.configuration_wizard_azure_ad()
                elif action == "Setup GitHub App Integration using AWS Lambda":
                    self.setup_aws_configuration()
                    if self.has_confirm_cf_permissions:
                        self.configuration_github_app_aws_lambda_setup()
                    else:
                        log.info(
                            "Unable to edit this attribute without CloudFormation permissions."
                        )
                elif action == "Setup AWS change detection":
                    self.setup_aws_configuration()
                    if self.has_cf_stacksets_permissions:
                        log.info(
                            f"IAMbic change detection relies on CloudTrail being enabled all IAMbic aware accounts. "
                            f"You can check that you have CloudTrail setup by going to "
                            f"https://{self.aws_default_region}.console.aws.amazon.com/cloudtrail/home\n"
                            f"If you do not have CloudTrail setup, you can set it up by going to "
                            f"https://{self.aws_default_region}.console.aws.amazon.com/cloudtrail/home?region={self.aws_default_region}#/create"
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
