import base64
from enum import Enum
from typing import List, Optional

import boto3
import botocore
from pydantic import BaseModel
from slack_bolt import App as SlackBoltApp

from noq_form.core.logger import log
from noq_form.core.utils import yaml


class Variable(BaseModel):
    key: str
    value: str


class AccountConfig(BaseModel):
    account_id: str
    org_id: Optional[str] = None
    account_name: Optional[str] = None
    default_region: Optional[str] = "us-east-1"
    aws_profile: Optional[str] = None
    assume_role_arn: Optional[str] = None
    external_id: Optional[str] = None
    role_access_tag: Optional[str] = None
    variables: Optional[List[Variable]] = []
    boto3_session_map: Optional[dict] = None

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
        if self.assume_role_arn and self.external_id:
            try:
                sts = session.client("sts")
                role = sts.assume_role(
                    RoleArn=self.assume_role_arn,
                    ExternalId=self.external_id,
                    RoleSessionName="NoqForm",
                )
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


class ExtendsConfigKey(Enum):
    AWS_SECRETS_MANAGER = "AWS_SECRETS_MANAGER"


class ExtendsConfig(BaseModel):
    key: ExtendsConfigKey
    value: str


class Config(BaseModel):
    accounts: List[AccountConfig]
    extends: List[ExtendsConfig] = []
    secrets: Optional[dict] = None
    role_access_tag: Optional[str] = "noq-authorized"
    variables: Optional[List[Variable]] = []
    slack_app: Optional[SlackBoltApp] = None
    sqs: Optional[dict] = {}
    slack: Optional[dict] = {}

    class Config:
        arbitrary_types_allowed = True

    def set_account_defaults(self):
        for elem, account in enumerate(self.accounts):
            if not account.role_access_tag:
                self.accounts[elem].role_access_tag = self.role_access_tag

            for variable in self.variables:
                if variable.key not in [av.key for av in account.variables]:
                    self.accounts[elem].variables.append(variable)

    def get_aws_secret(self, secret_arn: str) -> dict:
        """TODO: Secrets should be moved to the account to prevent an anti-pattern
        It also makes it required for every account to have access to the account the secret exists on
        Example: If the secret is in prod
          A build in the staging account won't work unless it has access to the prod secret
        """
        session = self.get_boto_session_from_arn(secret_arn)
        client = session.client(service_name="secretsmanager")
        get_secret_value_response = client.get_secret_value(SecretId=secret_arn)
        if "SecretString" in get_secret_value_response:
            return_val = get_secret_value_response["SecretString"]
        else:
            return_val = base64.b64decode(get_secret_value_response["SecretBinary"])

        return yaml.load(return_val)

    def configure_slack(self):
        if slack_bot_token := self.secrets.get("slack", {}).get("bot_token"):
            self.slack_app = SlackBoltApp(token=slack_bot_token)

    def combine_extended_configs(self):
        if self.extends:
            for extend in self.extends:
                if extend.key == ExtendsConfigKey.AWS_SECRETS_MANAGER:
                    for k, v in self.get_aws_secret(extend.value).items():
                        if not getattr(self, k):
                            setattr(self, k, v)

    def get_boto_session_from_arn(self, arn: str):
        region = arn.split(":")[3]
        account_id = arn.split(":")[4]
        account_config_map = {account.account_id: account for account in self.accounts}
        account_config = account_config_map[account_id]
        return account_config.get_boto3_session(region)

    @classmethod
    def load(cls, file_path: str):
        c = cls(file_path=file_path, **yaml.load(open(file_path)))
        c.combine_extended_configs()
        c.configure_slack()
        return c
