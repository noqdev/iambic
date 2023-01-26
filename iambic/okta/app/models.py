from __future__ import annotations

import asyncio
import json
from enum import Enum
from itertools import chain
from typing import Any, List, Optional

from pydantic import Field

from iambic.config.models import Config, OktaOrganization
from iambic.core.context import ExecutionContext
from iambic.core.iambic_enum import IambicManaged
from iambic.core.logger import log
from iambic.core.models import (
    AccountChangeDetails,
    BaseModel,
    BaseTemplate,
    ExpiryModel,
    ProposedChange,
    ProposedChangeType,
    TemplateChangeDetails,
)
from iambic.okta.group.utils import (
    create_group,
    get_group,
    maybe_delete_group,
    update_group_description,
    update_group_members,
    update_group_name,
)
from iambic.okta.models import Assignment, Group, Status


class OktaAppTemplateProperties(ExpiryModel, BaseModel):
    name: str = Field(..., description="Name of the app")
    owner: Optional[str] = Field(None, description="Owner of the app")
    status: Optional[Status] = Field(None, description="Status of the app")
    idp_name: str = Field(
        ...,
        description="Name of the identity provider that's associated with the group",
    )
    id: Optional[str] = Field(
        None, description="Unique App ID for the app. Usually it's {idp-name}-{name}"
    )
    description: Optional[str] = Field("", description="Description of the app")
    extra: Any = Field(None, description=("Extra attributes to store"))
    created: Optional[str] = Field("", description="Date the app was created")
    assignments: List[Assignment] = Field([], description="List of assignments")

    @property
    def resource_type(self) -> str:
        return "okta:app"

    @property
    def resource_id(self) -> str:
        return self.app_id


class OktaAppTemplate(BaseTemplate, ExpiryModel):
    template_type = "NOQ::Okta::App"
    properties: OktaAppTemplateProperties = Field(
        ..., description="Properties for the Okta App"
    )


async def get_app_template(okta_app) -> OktaAppTemplate:
    """Get a template for an app"""
    file_name = f"{okta_app.name}.yaml"
    app = OktaAppTemplate(
        file_path=f"okta/apps/{okta_app.idp_name}/{file_name}",
        template_type="NOQ::Okta::App",
        properties=OktaAppTemplateProperties(
            name=okta_app.name,
            status=okta_app.status,
            idp_name=okta_app.idp_name,
            id=okta_app.id,
            file_path="{}.yaml".format(okta_app.name),
            attributes=dict(),
            assignments=okta_app.assignments,
        ),
    )
    return app
