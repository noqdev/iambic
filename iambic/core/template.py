from __future__ import annotations

from typing import Type

from pydantic import Field

from iambic.core.models import BaseTemplate


class TemplateMixin:
    templates: list[Type[BaseTemplate]] = Field(
        description="The list of templates used for this provider."
    )

    @property
    def template_map(self) -> dict[str, Type[BaseTemplate]]:
        return {
            template.__fields__["template_type"].default: template
            for template in self.templates
        }
