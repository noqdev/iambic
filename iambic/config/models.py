from __future__ import annotations

import asyncio
import base64
import os
from enum import Enum
from typing import Any, List, Optional

import boto3
import googleapiclient.discovery
import ujson
from google.oauth2 import service_account
from okta.client import Client as OktaClient
from pydantic import Field
from slack_bolt import App as SlackBoltApp

from iambic.aws.models import AWSAccount, AWSOrganization
from iambic.core.models import BaseModel, Variable
from iambic.core.utils import aio_wrapper, yaml


class GoogleSubjects(BaseModel):
    domain: str
    service_account: str


class OktaOrganization(BaseModel):
    idp_name: str
    org_url: str
    api_token: str
    request_timeout: int = 60
    client: Optional[Any]

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
    read_only: Optional[bool] = Field(
        False,
        description="If set to True, iambic will only log drift instead of apply changes when drift is detected.",
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


class Config(BaseModel):
    aws: AWSConfig = Field(
        AWSConfig(),
        description="AWS configuration for iambic to use when managing AWS resources",
    )
    google_projects: List[GoogleProject] = []
    okta_organizations: List[OktaOrganization] = []
    extends: List[ExtendsConfig] = []
    secrets: Optional[dict] = None
    role_access_tag: Optional[str] = Field(
        "noq-authorized",
        description="The key of the tag used to store users and groups that can assume into the role the tag is on",
    )
    variables: Optional[List[Variable]] = Field(
        [],
        description="A list of variables to be used when creating templates. "
        "These apply to all aws_accounts but can be overwritten by an account.",
    )
    slack_app: Optional[str] = None
    sqs: Optional[dict] = {}
    slack: Optional[dict] = {}

    class Config:
        arbitrary_types_allowed = True

    def write(self, path: str):
        with open(path, "w") as f:
            f.write(yaml.dump(ujson.loads(self.json(indent=4))))

    async def setup_aws_accounts(self):
        for elem, account in enumerate(self.aws.accounts):
            if not account.role_access_tag:
                self.aws.accounts[elem].role_access_tag = self.role_access_tag

            for variable in self.variables:
                if variable.key not in [av.key for av in account.variables]:
                    self.aws.accounts[elem].variables.append(variable)

        account_map = {account.account_id: account for account in self.aws.accounts}
        config_account_idx_map = {
            account.account_id: idx for idx, account in enumerate(self.aws.accounts)
        }

        if self.aws and self.aws.organizations:
            orgs_accounts = await asyncio.gather(
                *[org.get_accounts(account_map) for org in self.aws.organizations]
            )
            for org_accounts in orgs_accounts:
                for account in org_accounts:
                    if not account.role_access_tag:
                        account.role_access_tag = self.role_access_tag
                    if (
                        account_elem := config_account_idx_map.get(account.account_id)
                    ) is not None:
                        self.aws.accounts[account_elem] = account
                    else:
                        self.aws.accounts.append(account)

    def get_aws_secret(self, extend: ExtendsConfig) -> dict:
        """TODO: Secrets should be moved to the account to prevent an anti-pattern
        It also makes it required for every account to have access to the account the secret exists on
        Example: If the secret is in prod
          A build in the staging account won't work unless it has access to the prod secret
        """
        secret_arn = extend.value
        region_name = secret_arn.split(":")[3]
        session = boto3.Session(region_name=region_name)
        if extend.assume_role_arn:
            sts = session.client("sts")
            role_params = dict(
                RoleArn=extend.assume_role_arn,
                RoleSessionName="iambic",
            )
            if extend.external_id:
                role_params["ExternalId"] = self.external_id
            role = sts.assume_role(**role_params)
            session = boto3.Session(
                region_name=region_name,
                aws_access_key_id=role["Credentials"]["AccessKeyId"],
                aws_secret_access_key=role["Credentials"]["SecretAccessKey"],
                aws_session_token=role["Credentials"]["SessionToken"],
            )

        client = session.client(service_name="secretsmanager")
        get_secret_value_response = client.get_secret_value(SecretId=secret_arn)
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

    def combine_extended_configs(self):
        if self.extends:
            for extend in self.extends:
                if extend.key == ExtendsConfigKey.AWS_SECRETS_MANAGER:
                    for k, v in self.get_aws_secret(extend).items():
                        if not getattr(self, k, None):
                            setattr(self, k, v)

    async def get_boto_session_from_arn(self, arn: str, region_name: str = None):
        region_name = region_name or arn.split(":")[3]
        account_id = arn.split(":")[4]
        aws_account_map = {account.account_id: account for account in self.aws.accounts}
        aws_account = aws_account_map[account_id]
        return await aws_account.get_boto3_session(region_name)

    @classmethod
    def load(cls, file_path: str):
        c = cls(file_path=file_path, **yaml.load(open(file_path)))
        c.combine_extended_configs()
        c.configure_slack()
        c.configure_google()
        c.configure_okta()
        return c
