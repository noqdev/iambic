from typing import List, Optional

import boto3
from pydantic import BaseModel

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

    def __str__(self):
        return f"{self.account_name} - ({self.account_id})"


class Config(BaseModel):
    accounts: List[AccountConfig]
    role_access_tag: Optional[str] = "noq-authorized"
    variables: Optional[List[Variable]] = []

    def set_account_defaults(self):
        for elem, account in enumerate(self.accounts):
            if not account.role_access_tag:
                self.accounts[elem].role_access_tag = self.role_access_tag

            for variable in self.variables:
                if variable.key not in [av.key for av in account.variables]:
                    self.accounts[elem].variables.append(variable)

    @classmethod
    def load(cls, file_path: str):
        return cls(file_path=file_path, **yaml.load(open(file_path)))
