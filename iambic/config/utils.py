from __future__ import annotations

import pathlib
import resource
from typing import TYPE_CHECKING

from iambic.core.logger import log
from iambic.core.utils import gather_templates

if TYPE_CHECKING:
    from iambic.config.dynamic_config import Config


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
