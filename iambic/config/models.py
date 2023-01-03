import base64
from enum import Enum
from typing import List, Optional

import boto3
import botocore
import googleapiclient.discovery
from google.oauth2 import service_account
from pydantic import BaseModel, Field, constr
from slack_bolt import App as SlackBoltApp

from iambic.aws.utils import RegionName
from iambic.core.logger import log
from iambic.core.utils import aio_wrapper, yaml


class Variable(BaseModel):
    key: str
    value: str


class AWSAccount(BaseModel):
    account_id: constr(min_length=12, max_length=12) = Field(
        None, description="The AWS Account ID"
    )
    org_id: Optional[str] = Field(
        None,
        description="A unique identifier designating the identity of the organization",
    )
    account_name: Optional[str] = None
    default_region: Optional[RegionName] = Field(
        RegionName.us_east_1,
        description="Default region to use when making AWS requests",
    )
    aws_profile: Optional[str] = Field(
        None,
        description="The AWS profile used when making calls to the account",
    )
    assume_role_arn: Optional[str] = Field(
        None,
        description="The role arn to assume into when making calls to the account",
    )
    external_id: Optional[str] = Field(
        None,
        description="The external id to use for assuming into a role when making calls to the account",
    )
    role_access_tag: Optional[str] = Field(
        None,
        description="The key of the tag used to store users and groups that can assume into the role the tag is on",
    )
    variables: Optional[List[Variable]] = Field(
        [],
        description="A list of variables to be used when creating templates",
    )
    boto3_session_map: Optional[dict] = None
    read_only: Optional[bool] = Field(
        False,
        description="If set to True, iambic will only log drift instead of apply changes when drift is detected.",
    )

    def get_boto3_session(self, region_name: str = None):
        region_name = region_name or self.default_region

        if self.boto3_session_map is None:
            self.boto3_session_map = {}
        elif boto3_session := self.boto3_session_map.get(region_name):
            return boto3_session

        if self.aws_profile:
            try:
                self.boto3_session_map[region_name] = boto3.Session(
                    profile_name=self.aws_profile, region_name=region_name
                )
            except Exception as err:
                log.exception(err)
            else:
                return self.boto3_session_map[region_name]

        session = boto3.Session(region_name=region_name)
        if self.assume_role_arn:
            try:
                sts = session.client("sts")
                role_params = dict(
                    RoleArn=self.assume_role_arn,
                    RoleSessionName="iambic",
                )
                if self.external_id:
                    role_params["ExternalId"] = self.external_id
                role = sts.assume_role(**role_params)
                self.boto3_session_map[region_name] = boto3.Session(
                    region_name=region_name,
                    aws_access_key_id=role["Credentials"]["AccessKeyId"],
                    aws_secret_access_key=role["Credentials"]["SecretAccessKey"],
                    aws_session_token=role["Credentials"]["SessionToken"],
                )
            except Exception as err:
                log.exception(err)
            else:
                return self.boto3_session_map[region_name]

        self.boto3_session_map[region_name] = session
        return self.boto3_session_map[region_name]

    def get_boto3_client(self, service: str, region_name: str = None):
        return self.get_boto3_session(region_name).client(
            service, config=botocore.client.Config(max_pool_connections=50)
        )

    def __str__(self):
        return f"{self.account_name} - ({self.account_id})"

    def __init__(self, **kwargs):
        super(AWSAccount, self).__init__(**kwargs)
        self.default_region = self.default_region.value


class GoogleSubjects(BaseModel):
    domain: str
    service_account: str


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


class Config(BaseModel):
    aws_accounts: List[AWSAccount]
    google_projects: List[GoogleProject] = []
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

    def set_account_defaults(self):
        for elem, account in enumerate(self.aws_accounts):
            if not account.role_access_tag:
                self.aws_accounts[elem].role_access_tag = self.role_access_tag

            for variable in self.variables:
                if variable.key not in [av.key for av in account.variables]:
                    self.aws_accounts[elem].variables.append(variable)

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

    def combine_extended_configs(self):
        if self.extends:
            for extend in self.extends:
                if extend.key == ExtendsConfigKey.AWS_SECRETS_MANAGER:
                    for k, v in self.get_aws_secret(extend).items():
                        if not getattr(self, k):
                            setattr(self, k, v)

    def get_boto_session_from_arn(self, arn: str, region_name: str = None):
        region_name = region_name or arn.split(":")[3]
        account_id = arn.split(":")[4]
        aws_account_map = {account.account_id: account for account in self.aws_accounts}
        aws_account = aws_account_map[account_id]
        return aws_account.get_boto3_session(region_name)

    @classmethod
    def load(cls, file_path: str):
        c = cls(file_path=file_path, **yaml.load(open(file_path)))
        c.combine_extended_configs()
        c.configure_slack()
        c.configure_google()
        return c

    @classmethod
    def noq_load(cls, file_path: str):
        c = cls(file_path=file_path, **yaml.load(open(file_path)))
        return c
