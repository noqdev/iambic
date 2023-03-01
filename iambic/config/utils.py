from __future__ import annotations

import pathlib

from iambic.core.utils import gather_templates


async def resolve_config_template_path(repo_dir: str) -> pathlib.Path:
    config_template_file_path = await gather_templates(repo_dir, "Core::Config")
    if len(config_template_file_path) == 0:
        raise RuntimeError(
            f"Unable to discover iambic Configuration in {repo_dir}. "
            "Create a configuration with the `NOQ::Core::Config` template type. "
            "You can run `iambic setup` to generate a configuration."
        )
    if len(config_template_file_path) > 1:
        # IAMbic supports 1 configuration per repo
        raise RuntimeError(
            f"Too many NOQ::Core::Config templates discovered. Found ({len(config_template_file_path)}). "
            f"Expected 1. Files: {','.join(config_template_file_path)}"
        )

    return pathlib.Path(config_template_file_path[0])
