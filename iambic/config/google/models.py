from typing import List, Optional

import googleapiclient.discovery
from google.oauth2 import service_account
from pydantic import BaseModel, Field

from iambic.core.models import Variable
from iambic.core.utils import aio_wrapper


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
