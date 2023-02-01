from __future__ import annotations

import asyncio
import base64
import os
import pathlib
from enum import Enum
from typing import Any, List, Optional

import googleapiclient.discovery
from google.oauth2 import service_account
from okta.client import Client as OktaClient
from pydantic import BaseModel, Field
from slack_bolt import App as SlackBoltApp

from iambic.aws.models import AWSAccount, AWSOrganization
from iambic.core.iambic_enum import IambicManaged
from iambic.core.logger import log
from iambic.core.models import BaseTemplate, Variable
from iambic.core.utils import aio_wrapper, sort_dict, yaml

CURRENT_IAMBIC_VERSION = "1"


class GoogleSubjects(BaseModel):
    domain: str
    service_account: str


class OktaOrganization(BaseModel):
    idp_name: str
    org_url: str
    api_token: str
    request_timeout: int = 60
    client: Any = None  # OktaClient

    class Config:
        arbitrary_types_allowed = True

    async def get_okta_client(self):
        if not self.client:
            self.client = OktaClient(
                {
                    "orgUrl": self.org_url,
                    "token": self.api_token,
                    "requestTimeout": self.request_timeout,
                }
            )
        return self.client


class GoogleProject(BaseModel):
    project_id: str
    project_name: Optional[str]
    subjects: list[GoogleSubjects]
    type: str
    private_key_id: str
    private_key: str
    client_email: str
    client_id: str
    auth_uri: str
    token_uri: str
    auth_provider_x509_cert_url: str
    client_x509_cert_url: str
    variables: Optional[List[Variable]] = Field(
        [],
        description="A list of variables to be used when creating templates",
    )
    iambic_managed: Optional[IambicManaged] = Field(
        IambicManaged.UNDEFINED,
        description="Controls the directionality of iambic changes",
    )
    _service_connection_map: dict = {}

    def __str__(self):
        if self.project_name:
            return f"{self.project_name} - ({self.project_id})"

        return self.project_id

    async def get_service_connection(
        self,
        service_name: str,
        service_path: str,
        domain: str,
        cache_discovery: bool = False,
    ):
        # sourcery skip: raise-specific-error
        key = f"{domain}:{service_name}:{service_path}"
        if not os.environ.get("TESTING"):
            if service_conn := self._service_connection_map.get(key):
                return service_conn

        admin_credentials = service_account.Credentials.from_service_account_info(
            self.dict(
                include={
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
            ),
            scopes=[
                "https://www.googleapis.com/auth/admin.directory.user.security",
                "https://www.googleapis.com/auth/admin.reports.audit.readonly",
                "https://www.googleapis.com/auth/admin.directory.user",
                "https://www.googleapis.com/auth/admin.directory.group",
                "https://www.googleapis.com/auth/admin.directory.group.member",
            ],
        )

        admin_delegated_credentials = None

        for s in self.subjects:
            if s.domain == domain:
                admin_delegated_credentials = admin_credentials.with_subject(
                    s.service_account
                )
                break
        if not admin_delegated_credentials:
            raise Exception(f"Could not find service account for domain {domain}")

        self._service_connection_map[key] = await aio_wrapper(
            googleapiclient.discovery.build,
            service_name,
            service_path,
            credentials=admin_delegated_credentials,
            cache_discovery=cache_discovery,
            thread_sensitive=True,
        )
        return self._service_connection_map[key]


class ExtendsConfigKey(Enum):
    AWS_SECRETS_MANAGER = "AWS_SECRETS_MANAGER"
    LOCAL_FILE = "LOCAL_FILE"


class ExtendsConfig(BaseModel):
    key: ExtendsConfigKey
    value: str
    assume_role_arn: Optional[str]
    external_id: Optional[str]


class AWSConfig(BaseModel):
    organizations: list[AWSOrganization] = Field(
        [], description="A list of AWS Organizations to be managed by iambic"
    )
    accounts: List[AWSAccount] = Field(
        [], description="A list of AWS Accounts to be managed by iambic"
    )
    min_accounts_required_for_wildcard_included_accounts: int = Field(
        3,
        description=(
            "Iambic will set included_accounts=* on imported resources that exist on all accounts if the minimum number of accounts is met."
        ),
    )

    @property
    def hub_role_arn(self):
        if self.organizations:
            return self.organizations[0].hub_role_arn
        else:
            return [
                account.hub_role_arn
                for account in self.accounts
                if account.hub_role_arn
            ][0]


class Config(BaseTemplate):
    aws: AWSConfig = Field(
        AWSConfig(),
        description="AWS configuration for iambic to use when managing AWS resources",
    )
    google_projects: List[GoogleProject] = []
    okta_organizations: List[OktaOrganization] = []
    extends: List[ExtendsConfig] = []
    secrets: Optional[dict] = Field(
        description="secrets should only be used in memory and never serialized out",
        exclude=True,
    )
    variables: Optional[List[Variable]] = Field(
        [],
        description="A list of variables to be used when creating templates. "
        "These apply to all aws_accounts but can be overwritten by an account.",
    )
    slack_app: Optional[str] = None
    sqs_cloudtrail_changes_queues: Optional[list[str]] = []
    slack: Optional[dict] = {}
    template_type: str = "NOQ::Core::Config"
    version: str = Field(
        description="Do not change! The version of iambic this repo is compatible with.",
    )

    @property
    def aws_is_setup(self) -> bool:
        return bool(self.aws and (self.aws.accounts or self.aws.organizations))

    class Config:
        arbitrary_types_allowed = True

    async def setup_aws_accounts(self):
        if not self.aws_is_setup:
            await self.configure_plugins()
            return

        for elem, account in enumerate(self.aws.accounts):
            for variable in self.variables:
                if variable.key not in [av.key for av in account.variables]:
                    self.aws.accounts[elem].variables.append(variable)

        config_account_idx_map = {
            account.account_id: idx for idx, account in enumerate(self.aws.accounts)
        }
        if self.aws.organizations:
            if any(account.hub_role_arn for account in self.aws.accounts):
                raise AttributeError(
                    "You cannot specify a hub_role_arn on an AWS Account if you are using an AWS Organization"
                )

            orgs_accounts = await asyncio.gather(
                *[org.get_accounts() for org in self.aws.organizations]
            )
            for org_accounts in orgs_accounts:
                for account in org_accounts:
                    if (
                        account_elem := config_account_idx_map.get(account.account_id)
                    ) is not None:
                        self.aws.accounts[
                            account_elem
                        ].hub_session_info = account.hub_session_info
                        self.aws.accounts[
                            account_elem
                        ].identity_center_details = account.identity_center_details
                    else:
                        log.warning(
                            "Account not found in config. Account will be ignored.",
                            account_id=account.account_id,
                            account_name=account.account_name,
                        )
        elif self.aws.accounts:
            hub_account = [
                account for account in self.aws.accounts if account.hub_role_arn
            ]
            if len(hub_account) > 1:
                raise AttributeError(
                    "Only one AWS Account can specify the hub_role_arn"
                )
            elif not hub_account:
                raise AttributeError(
                    "One of the AWS Accounts must define the hub_role_arn"
                )
            else:
                hub_account = hub_account[0]
                await hub_account.set_hub_session_info()
                hub_session_info = hub_account.hub_session_info
                if not hub_session_info:
                    raise Exception("Unable to assume into the hub_role_arn")
                for account in self.aws.accounts:
                    if account.account_id != hub_account.account_id:
                        account.hub_session_info = hub_session_info

        await self.configure_plugins()

    async def get_aws_secret(self, extend: ExtendsConfig) -> dict:
        """TODO: Secrets should be moved to the account to prevent an anti-pattern
        It also makes it required for every account to have access to the account the secret exists on
        Example: If the secret is in prod
          A build in the staging account won't work unless it has access to the prod secret
        """
        assume_role_arn = extend.assume_role_arn
        secret_arn = extend.value
        region_name = secret_arn.split(":")[3]
        secret_account_id = secret_arn.split(":")[4]
        aws_account_map = {account.account_id: account for account in self.aws.accounts}
        session = None

        if aws_account := aws_account_map.get(secret_account_id):
            if assume_role_arn == aws_account.spoke_role_arn:
                session = await aws_account.get_boto3_session(region_name=region_name)

        if not session:
            boto3_session = await self.aws.organizations[0].get_boto3_session()
            secret_account = AWSAccount(
                account_id=secret_account_id,
                account_name="Secret_Account",
                spoke_role_arn=assume_role_arn,
                hub_session_info=dict(boto3_session=boto3_session),
                boto3_session_map={},
            )
            session = await secret_account.get_boto3_session(region_name=region_name)

        try:
            client = session.client(service_name="secretsmanager")
            get_secret_value_response = client.get_secret_value(SecretId=secret_arn)
        except Exception:
            log.exception(
                "Unable to retrieve the AWS secret using the provided assume_role_arn",
                assume_role_arn=assume_role_arn,
                secret_arn=extend.value,
            )
            raise

        if "SecretString" in get_secret_value_response:
            return_val = get_secret_value_response["SecretString"]
        else:
            return_val = base64.b64decode(get_secret_value_response["SecretBinary"])

        return yaml.load(return_val)

    def configure_slack(self):
        if self.secrets and (
            slack_bot_token := self.secrets.get("slack", {}).get("bot_token")
        ):
            self.slack_app = SlackBoltApp(token=slack_bot_token)

    def configure_google(self):
        if self.secrets and (google_secrets := self.secrets.get("google")):
            self.google_projects = [GoogleProject(**x) for x in google_secrets]

    def configure_okta(self):
        if self.secrets and (okta_secrets := self.secrets.get("okta")):
            self.okta_organizations = [OktaOrganization(**x) for x in okta_secrets]

    async def combine_extended_configs(self):
        if self.extends:
            for extend in self.extends:
                if extend.key == ExtendsConfigKey.AWS_SECRETS_MANAGER:
                    for k, v in (await self.get_aws_secret(extend)).items():
                        if not getattr(self, k, None):
                            setattr(self, k, v)
                if extend.key == ExtendsConfigKey.LOCAL_FILE:
                    dir_path = os.path.dirname(self.file_path)
                    extend_path = os.path.join(dir_path, extend.value)
                    with open(extend_path, "r") as ymlfile:
                        extend_config = yaml.load(ymlfile)
                    for k, v in extend_config.items():
                        if not getattr(self, k, None):
                            setattr(self, k, v)

    async def get_boto_session_from_arn(self, arn: str, region_name: str = None):
        region_name = region_name or arn.split(":")[3]
        account_id = arn.split(":")[4]
        aws_account_map = {account.account_id: account for account in self.aws.accounts}
        aws_account = aws_account_map[account_id]
        return await aws_account.get_boto3_session(region_name)

    async def configure_plugins(self):
        await self.combine_extended_configs()
        self.configure_slack()
        self.configure_google()
        self.configure_okta()

    @classmethod
    def load(cls, file_path: str):
        if isinstance(file_path, pathlib.Path):
            file_path = str(file_path)
        c = cls(file_path=file_path, **yaml.load(open(file_path)))
        return c

    def dict(
        self,
        *,
        include: Optional[
            Union["AbstractSetIntStr", "MappingIntStrAny"]  # noqa
        ] = None,
        exclude: Optional[
            Union["AbstractSetIntStr", "MappingIntStrAny"]  # noqa
        ] = None,
        by_alias: bool = False,
        skip_defaults: Optional[bool] = None,
        exclude_unset: bool = True,
        exclude_defaults: bool = False,
        exclude_none: bool = True,
    ) -> "DictStrAny":  # noqa
        required_exclude = {
            "google_projects",
            "okta_organizations",
            "slack_app",
            "secrets",
            "file_path",
        }

        if exclude:
            exclude.update(required_exclude)
        else:
            exclude = required_exclude

        return super().dict(
            include=include,
            exclude=exclude,
            by_alias=by_alias,
            skip_defaults=skip_defaults,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
        )

    def write(self, exclude_none=True, exclude_unset=False, exclude_defaults=True):
        input_dict = self.dict(
            exclude_none=exclude_none,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
        )
        sorted_input_dict = sort_dict(
            input_dict,
            [
                "template_type",
                "version",
            ],
        )

        file_path = os.path.expanduser(self.file_path)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w") as f:
            f.write(yaml.dump(sorted_input_dict))

        log.info("Config successfully written", config_location=file_path)
