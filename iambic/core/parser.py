from __future__ import annotations

from pydantic import ValidationError

from iambic.config.templates import TEMPLATES
from iambic.core.logger import log
from iambic.core.models import BaseTemplate
from iambic.core.utils import transform_comments, yaml


def load_templates(template_paths: list[str]) -> list[BaseTemplate]:
    templates = []

    for template_path in template_paths:
        try:
            template_dict = transform_comments(yaml.load(open(template_path)))
            if template_dict["template_type"] in ["NOQ::Core::Config"]:
                continue
            template_cls = TEMPLATES.template_map[template_dict["template_type"]]
            template_cls.update_forward_refs()
            templates.append(template_cls(file_path=template_path, **template_dict))
        except KeyError:
            log.critical(
                "Invalid template type",
                file_path=template_path,
                template_type=template_dict["template_type"],
            )
            # We should allow to continue to allow unknown template type; otherwise,
            # we cannot support forward or backward compatibility during version changes.
        except ValidationError:
            log.critical("Invalid template structure", file_path=template_path)
            raise

    return templates
