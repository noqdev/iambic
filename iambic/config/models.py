from __future__ import annotations

import os
from enum import Enum
from typing import Any, List, Optional

import googleapiclient.discovery
from google.oauth2 import service_account
from okta.client import Client as OktaClient
from pydantic import BaseModel, Field, validator

from iambic.core.iambic_enum import IambicManaged
from iambic.core.models import Variable
from iambic.core.utils import aio_wrapper
from iambic.plugins.v0_1_0.aws.models import AWSAccount, AWSOrganization


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

    @validator("organizations")
    def validate_organizations(cls, organizations):
        if len(organizations) > 1:
            raise ValueError("Only one AWS Organization is supported at this time.")
        return organizations

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
