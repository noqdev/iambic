from __future__ import annotations

import pathlib
import resource
from iambic.config.dynamic_config import CoreConfig

from iambic.core.logger import log
from iambic.core.utils import gather_templates


async def resolve_config_template_path(repo_dir: str) -> pathlib.Path:
    config_template_file_path = await gather_templates(repo_dir, "Core::Config")
    if len(config_template_file_path) == 0:
        raise RuntimeError(
            f"Unable to discover Iambic Configuration in {repo_dir}. "
            "Please create a configuration with the `NOQ::Core::Config` template type."
        )
    if len(config_template_file_path) > 1:
        # IAMbic supports 1 configuration per repo
        raise RuntimeError(
            f"Too many NOQ::Core::Config templates discovered. Found ({len(config_template_file_path)}). "
            f"Expected 1. Files: {','.join(config_template_file_path)}"
        )

    return pathlib.Path(config_template_file_path[0])


def check_and_update_resource_limit():
    soft_limit, hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft_limit < CoreConfig.minimum_ulimit:
        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, (CoreConfig.minimum_ulimit, hard_limit))
        except PermissionError:
            log.warning("Cannot increase resource limit: the process does not have permission.")
        except Exception:
            log.warning("Unable to increase resource limit: please manually update the soft limit to atleast 4096.")
