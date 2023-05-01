from __future__ import annotations

import json
import os
import sys
import time
import traceback
from functools import partial
from typing import Union

from pydantic import ValidationError
from ruamel.yaml.scanner import ScannerError

from iambic.config.templates import TEMPLATES
from iambic.core.logger import log
from iambic.core.models import BaseTemplate
from iambic.core.utils import transform_comments, yaml

# we must avoid import multiprocessing pool in the module loading time
if os.environ.get("AWS_LAMBDA_FUNCTION_NAME", False):
    from multiprocessing import cpu_count

    from iambic.vendor.lambda_multiprocessing import Pool
else:
    from multiprocessing import Pool, cpu_count


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


def load_template(template_path: str, raise_validation_err: bool = True) -> dict:
    try:
        template_dict = transform_comments(yaml.load(open(template_path)))
        template_type = template_dict.get("template_type")
        if template_type and template_type not in ["NOQ::Core::Config"]:
            template_dict["file_path"] = template_path
            return template_dict
    except ScannerError as err:
        log.critical(
            "Invalid template structure", file_path=template_path, error=repr(err)
        )
        if raise_validation_err:
            raise ValueError(f"{template_path} template has validation error.") from err


def load_templates(
    template_paths: list[str], raise_validation_err: bool = True
) -> list[BaseTemplate]:
    templates = []
    load_template_fn = partial(load_template, raise_validation_err=raise_validation_err)
    with Pool(max(1, cpu_count() // 2)) as p:
        template_dicts = p.map(load_template_fn, template_paths)
        if getattr(sys, "gettrace", None):
            # When in debug mode, subprocesses can exit
            # before debugger can attach
            # https://github.com/microsoft/debugpy/issues/712
            time.sleep(0.5)

    for template_dict in template_dicts:
        if not template_dict:
            continue

        try:
            template_cls = TEMPLATES.template_map[template_dict["template_type"]]
            template_cls.update_forward_refs()
            templates.append(template_cls(**template_dict))
        except KeyError:
            log.critical(
                "Invalid template type",
                file_path=template_dict["file_path"],
                template_type=template_dict["template_type"],
            )
            # We should allow to continue to allow unknown template type; otherwise,
            # we cannot support forward or backward compatibility during version changes.
        except ValidationError as err:
            log.critical(
                "Invalid template structure",
                file_path=template_dict["file_path"],
                error=repr(err),
            )
            if raise_validation_err:
                hints = format_validation_error(err, template_dict)
                raise ValueError(
                    f"{template_dict['file_path']} template has validation error. \n{hints}"
                ) from err

    return templates
