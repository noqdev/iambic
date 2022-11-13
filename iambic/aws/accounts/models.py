from typing import List, Optional

import boto3
import botocore
from pydantic import BaseModel, Field, constr

from iambic.aws.utils import RegionName
from iambic.core.logger import log
from iambic.core.models import Variable


class AWSAccountTemplate(BaseModel):
    template_type = "NOQ::AWS::Account"
    account_id: constr(min_length=12, max_length=12)
    org_id: Optional[str] = Field(
        None,
        description="A unique identifier designating the identity of the organization",
    )
    account_name: Optional[str] = None
    default_region: RegionName = Field(
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

    async def get_boto3_session(self, region_name: Optional[str] = None):
        region_name = region_name or self.default_region.value

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

    async def get_boto3_client(self, service: str, region_name: Optional[str] = None):
        session = await self.get_boto3_session(region_name)
        return session.client(
            service, config=botocore.client.Config(max_pool_connections=50)
        )

    def __str__(self):
        return f"{self.account_name} - ({self.account_id})"

    def __init__(self, **kwargs):
        super(AWSAccountTemplate, self).__init__(**kwargs)
        self.default_region = self.default_region.value
