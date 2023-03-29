from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from iambic.core.models import (
    BaseModel,
    BaseTemplate,
    ExpiryModel,
    TemplateChangeDetails,
)

EXAMPLE_LOCAL_DATABASE_TEMPLATE_TYPE = "NOQ::Example::LocalDatabase"

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.example.iambic_plugin import ExampleConfig


class ExampleLocalDatabaseTemplateProperties(BaseModel):
    name: str = Field(..., description="name of Local Database")

    @property
    def resource_type(self) -> str:
        return "example:local_database:properties"

    @property
    def resource_id(self) -> str:
        return self.name


class ExampleLocalDatabaseTemplate(BaseTemplate, ExpiryModel):
    template_type = EXAMPLE_LOCAL_DATABASE_TEMPLATE_TYPE
    properties: ExampleLocalDatabaseTemplateProperties = Field(
        ..., description="Properties for Example Local Database Template"
    )
    name: str = Field(..., description="name of Local Database")

    @property
    def resource_type(self) -> str:
        return "example:local_database"

    @property
    def resource_id(self) -> str:
        return self.name

    async def apply(self, config: ExampleConfig) -> TemplateChangeDetails:
        template_changes = TemplateChangeDetails(
            resource_id=self.resource_id,
            resource_type=self.template_type,
            template_path=self.file_path,
        )
        template_changes.proposed_changes = []
        return template_changes
