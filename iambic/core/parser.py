from __future__ import annotations

from iambic.config.templates import TEMPLATE_TYPE_MAP
from iambic.core.logger import log
from iambic.core.models import BaseTemplate
from iambic.core.utils import yaml


def load_templates(template_paths: list[str]) -> list[BaseTemplate]:
    templates = []

    for template_path in template_paths:
        try:
            template_dict = yaml.load(open(template_path))
            template_cls = TEMPLATE_TYPE_MAP[template_dict["template_type"]]
            template_cls.update_forward_refs()
            templates.append(template_cls(file_path=template_path, **template_dict))
        except KeyError:
            log.critical(
                "Invalid template type",
                file_path=template_path,
                template_type=template_dict["template_type"],
            )
            raise

    return templates
