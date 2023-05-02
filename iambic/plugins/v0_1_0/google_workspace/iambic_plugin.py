from __future__ import annotations

import os
import typing
from typing import TYPE_CHECKING, Any, Optional

import googleapiclient.discovery
from google.oauth2 import service_account
from pydantic import BaseModel, Field, SecretStr, validator

from iambic.core.iambic_enum import IambicManaged
from iambic.core.iambic_plugin import ProviderPlugin
from iambic.core.models import Variable
from iambic.core.utils import aio_wrapper
from iambic.plugins.v0_1_0 import PLUGIN_VERSION
from iambic.plugins.v0_1_0.google_workspace.group.models import (
    GoogleWorkspaceGroupTemplate,
)
from iambic.plugins.v0_1_0.google_workspace.handlers import (
    import_google_resources,
    load,
)

if TYPE_CHECKING:  # pragma: no cover
    MappingIntStrAny = typing.Mapping[int | str, Any]
    AbstractSetIntStr = typing.AbstractSet[int | str]


class GoogleSubject(BaseModel):
    domain: str
    service_account: str


class GoogleProject(BaseModel):
    project_id: str
    project_name: Optional[str]
    subjects: list[GoogleSubject]
    type: str
    private_key_id: str
    private_key: SecretStr
    client_email: str
    client_id: str
    auth_uri: str
    token_uri: str
    auth_provider_x509_cert_url: str
    client_x509_cert_url: str
    variables: Optional[list[Variable]] = Field(
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
        if self._service_connection_map.get(key):
            return self._service_connection_map[key]
        if not os.environ.get("TESTING"):
            if service_conn := self._service_connection_map.get(key):
                return service_conn
        credentials = self.dict(
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
        )
        credentials["private_key"] = credentials["private_key"].get_secret_value()
        admin_credentials = service_account.Credentials.from_service_account_info(
            credentials,
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


class GoogleWorkspaceConfig(BaseModel):
    workspaces: list[GoogleProject]

    @validator(
        "workspaces", allow_reuse=True
    )  # the need of allow_reuse is possibly related to how we handle inheritance
    def validate_google_workspaces(cls, workspaces: list[GoogleProject]):
        project_id_set = set()
        for workspace in workspaces:
            if workspace.project_id in project_id_set:
                raise ValueError(
                    f"project_id must be unique within workspaces: {workspace.project_id}"
                )
            else:
                project_id_set.add(workspace.project_id)
        return workspaces

    def get_workspace(self, project_id: str) -> GoogleProject:
        for w in self.workspaces:
            if w.project_id == project_id:
                return w
        raise Exception(f"Could not find workspace for project_id {project_id}")


IAMBIC_PLUGIN = ProviderPlugin(
    config_name="google_workspace",
    version=PLUGIN_VERSION,
    provider_config=GoogleWorkspaceConfig,
    requires_secret=True,
    async_import_callable=import_google_resources,
    async_load_callable=load,
    templates=[
        GoogleWorkspaceGroupTemplate,
    ],
)
