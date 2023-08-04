from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING

from iambic.core.logger import log
from iambic.core.utils import gather_templates

if TYPE_CHECKING:
    from iambic.config.dynamic_config import Config


CF_INVALID_TAGS_MSG = "Format has to be either blank or `key1=value1"


async def resolve_config_template_path(repo_dir: str) -> pathlib.Path:
    config_template_file_path = await gather_templates(repo_dir, "Core::Config")
    if len(config_template_file_path) == 0:
        raise RuntimeError(
            f"Unable to discover IAMbic Configuration in {repo_dir}. "
            "Create a configuration with the `NOQ::Core::Config` template type. "
            "You can run `iambic setup` to generate a configuration."
        )
    if len(config_template_file_path) > 1:
        # IAMbic supports 1 configuration per repo
        raise RuntimeError(
            f"Too many NOQ::Core::Config templates discovered. Found ({len(config_template_file_path)}). "
            f"Expected 1. Files: {','.join([str(x) for x in config_template_file_path])}"
        )

    return pathlib.Path(config_template_file_path[0])


def check_and_update_resource_limit(config: Config):
    try:
        import resource
    except ImportError:
        return
    soft_limit, hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
    minimum_ulimit = 64000
    if config.core:
        minimum_ulimit = config.core.minimum_ulimit
    if soft_limit < minimum_ulimit:
        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, (minimum_ulimit, hard_limit))
        except PermissionError:
            log.warning(
                "Cannot increase resource limit: the process does not have permission.",
                current_ulimit=soft_limit,
                desired_ulimit=minimum_ulimit,
            )
        except Exception:
            log.warning(
                "Unable to increase resource limit: please manually update the soft limit.",
                current_ulimit=soft_limit,
                desired_ulimit=minimum_ulimit,
            )


def aws_cf_parse_key_value_string(key_value_string):
    # This function is here because we don't have an abstraction for plugin to customize wizard setup
    # raw_key_value_string is a list of key value pairs separated by comma.
    # Examples: "k1=v1,k2='v  2',k3,k4"
    # https://github.com/aws/aws-cli/blob/96e5992ea216d7d951585c5050de589061f4e8fe/awscli/customizations/emr/emrutils.py#L28
    key_value_list = []
    if key_value_string:
        raw_key_value_list = key_value_string.split(",")
        for kv in raw_key_value_list:
            kv = kv.strip()
            if kv.find("=") == -1:
                key, value = kv, ""
            else:
                key, value = kv.split("=", 1)
            if len(key) < 1:
                raise ValueError("key must have at least one character")
            key_value_list.append({"Key": key, "Value": value})
        return key_value_list
    else:
        return None


def validate_aws_cf_input_tags(s):
    # This function is here because we don't have an abstraction for plugin to customize wizard setup
    try:
        tags = aws_cf_parse_key_value_string(s)
        if len(s) > 0 and len(tags) == 0:
            return CF_INVALID_TAGS_MSG
        return True
    except Exception:
        return CF_INVALID_TAGS_MSG
