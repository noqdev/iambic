from __future__ import annotations

from pydantic import ValidationError

from iambic.config.templates import TEMPLATE_TYPE_MAP
from iambic.core.logger import log
from iambic.core.models import BaseTemplate
from iambic.core.utils import transform_commments, yaml


def load_templates(template_paths: list[str]) -> list[BaseTemplate]:
    templates = []

    for template_path in template_paths:
        try:
            template_dict = transform_commments(yaml.load(open(template_path)))
            if template_dict["template_type"] in ["NOQ::Core::Config"]:
                continue
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
        except ValidationError:
            log.critical("Invalid template structure", file_path=template_path)
            raise

    return templates
