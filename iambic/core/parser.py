from __future__ import annotations

import json
import traceback
from typing import Union

from pydantic import ValidationError
from ruamel.yaml.scanner import ScannerError

from iambic.config.templates import TEMPLATES
from iambic.core.logger import log
from iambic.core.models import BaseTemplate
from iambic.core.utils import transform_comments, yaml


# line number is zero-th based
def resolve_location(loc_list: list[str], ruamel_dict) -> Union[None, int]:
    local_loc_list = loc_list
    local_ruamel_dict = ruamel_dict
    last_known_location = None
    if len(local_loc_list) == 0:
        return None
    while len(local_loc_list) > 1:
        lookup_key = local_loc_list[0]
        peek_ruamel_dict = ruamel_dict.get(str.lower(lookup_key), None)
        if peek_ruamel_dict is None:
            return None
        else:
            last_known_location = local_ruamel_dict.lc.data.get(str.lower(lookup_key))
        local_ruamel_dict = ruamel_dict.get(str.lower(lookup_key), None)
        local_loc_list = loc_list[1:]
    line_info = local_ruamel_dict.lc.data.get(str.lower(local_loc_list[0]), None)
    if line_info is None:
        if last_known_location is not None:
            return last_known_location[0]
        else:
            return None
    else:
        return line_info[0]


def format_validation_error(err, ruamel_dict):
    try:
        errors = json.loads(err.json())
        lines = []
        for error in errors:
            if error["type"] == "value_error.missing":
                line_num = resolve_location(error["loc"], ruamel_dict)
                canonical_key = str.lower(".".join(error["loc"]))
                if line_num is not None:
                    missing_key = str.lower(error["loc"][-1])
                    lines.append(
                        f"Missing Field: `{missing_key}` around line {line_num+1}"
                    )
                else:
                    lines.append(f"Missing Field: `{canonical_key}`")
            if error["type"].startswith("type_error"):
                line_num = resolve_location(error["loc"], ruamel_dict)
                canonical_key = str.lower(".".join(error["loc"]))
                lines.append(f"line {line_num+1}: `{canonical_key}` has type issue")
        return "\n".join(lines)
    except Exception:
        # need to still return something to avoid to downstream formatting
        captured_traceback = traceback.format_exc()
        return f"Unable to compute hints: {captured_traceback}"


def load_templates(
    template_paths: list[str], raise_validation_err: bool = True
) -> list[BaseTemplate]:
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
        except (ValidationError, ScannerError) as err:
            log.critical(
                "Invalid template structure", file_path=template_path, error=repr(err)
            )
            if raise_validation_err:
                if isinstance(err, ValidationError):
                    hints = format_validation_error(err, template_dict)
                else:
                    hints = ""
                raise ValueError(
                    f"{template_path} template has validation error. \n{hints}"
                ) from err

    return templates
