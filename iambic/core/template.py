from __future__ import annotations

from typing import Type

from iambic.core.models import BaseTemplate


class ConfigMixin:
    @property
    def templates(self) -> list[Type[BaseTemplate]]:
        raise NotImplementedError

    @property
    def template_map(self) -> dict[str, Type[BaseTemplate]]:
        return {
            template.__fields__["template_type"].default: template
            for template in self.templates
        }
