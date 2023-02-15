from __future__ import annotations

from iambic.core.models import BaseTemplate


class DynamicTemplateRef:
    templates = []

    @classmethod
    def set_templates(cls, templates):
        cls.templates = templates

    @property
    def template_map(self) -> dict[str, BaseTemplate]:
        return {
            template.__fields__["template_type"].default: template
            for template in self.templates
        }


TEMPLATES = DynamicTemplateRef()
