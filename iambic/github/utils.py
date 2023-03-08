from __future__ import annotations

import glob
import os

from iambic.core.logger import log


def create_workflow_files(
    repo_dir: str, repo_name: str, commit_email: str, assume_role_arn: str, region: str
):
    replacement_val_map = {
        # Leave the example here
        # "__TEMPLATE_IAMBIC_COMMIT_EMAIL": commit_email,
    }

    file_paths = glob.glob(f"{os.path.dirname(__file__)}/**/*.yaml", recursive=True)
    file_paths += glob.glob(f"{os.path.dirname(__file__)}/**/*.yml", recursive=True)

    workflows_dir = f"{str(repo_dir)}/.github/workflows"
    os.makedirs(workflows_dir, exist_ok=True)

    for file_path in file_paths:
        with open(file_path, mode="r") as f:
            file_content = f.read()
            for k, v in replacement_val_map.items():
                file_content = file_content.replace(k, v)

        with open(f"{workflows_dir}/{os.path.basename(file_path)}", mode="w") as f:
            f.write(file_content)

    log.info("Created workflow files successfully.", file_location=workflows_dir)
