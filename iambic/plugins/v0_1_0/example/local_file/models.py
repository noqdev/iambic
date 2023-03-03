from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from iambic.core.context import ExecutionContext
from iambic.core.models import (
    BaseModel,
    BaseTemplate,
    ExpiryModel,
    ProposedChange,
    ProposedChangeType,
    TemplateChangeDetails,
)

EXAMPLE_LOCAL_FILE_TEMPLATE_TYPE = "NOQ::Example::LocalFile"

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.example.iambic_plugin import ExampleConfig


class ExampleLocalFileTemplateProperties(BaseModel):
    name: str = Field(..., description="name of local file")

    @property
    def resource_type(self) -> str:
        return "example:local_file:properties"

    @property
    def resource_id(self) -> str:
        return self.name


class ExampleLocalFileTemplate(BaseTemplate, ExpiryModel):
    template_type = EXAMPLE_LOCAL_FILE_TEMPLATE_TYPE
    properties: ExampleLocalFileTemplateProperties = Field(
        ..., description="Properties for Example Local File Template"
    )
    name: str = Field(..., description="name of local file")

    @property
    def resource_type(self) -> str:
        return "example:local_file"

    @property
    def resource_id(self) -> str:
        return self.name

    async def apply(
        self, config: ExampleConfig, context: ExecutionContext
    ) -> TemplateChangeDetails:
        template_changes = TemplateChangeDetails(
            resource_id=self.resource_id,
            resource_type=self.template_type,
            template_path=self.file_path,
        )
        if self.delete:
            template_changes.proposed_changes = [
                ProposedChange(change_type=ProposedChangeType.DELETE)
            ]
        else:
            template_changes.proposed_changes = []
        return template_changes
