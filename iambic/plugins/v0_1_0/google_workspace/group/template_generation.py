from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

from iambic.core.logger import log
from iambic.core.models import ExecutionMessage
from iambic.core.template_generation import (
    create_or_update_template as common_create_or_update_template,
)
from iambic.core.template_generation import (
    delete_orphaned_templates,
    get_existing_template_map,
)
from iambic.plugins.v0_1_0.google_workspace.group.models import (
    GOOGLE_GROUP_TEMPLATE_TYPE,
    GoogleWorkspaceGroupTemplate,
)
from iambic.plugins.v0_1_0.google_workspace.group.utils import list_groups

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.google_workspace.iambic_plugin import (
        GoogleProject,
        GoogleWorkspaceConfig,
    )


def get_resource_dir_args(domain: str) -> list:
    return ["group", domain]


def get_response_dir(
    exe_message: ExecutionMessage, google_project: GoogleProject, domain: str
) -> str:
    dir_args = get_resource_dir_args(domain)
    dir_args.append("templates")
    if exe_message.provider_id:
        return exe_message.get_directory(*dir_args)
    else:
        return exe_message.get_directory(google_project.project_id, *dir_args)


def get_group_dir(
    base_dir: str,
    domain: str,
) -> str:
    return str(
        os.path.join(
            base_dir, "resources", "google_workspace", *get_resource_dir_args(domain)
        )
    )


def get_templated_resource_file_path(
    resource_dir: str,
    resource_email: str,
) -> str:
    unwanted_chars = ["}}_", "}}", ".", "-", " "]
    resource_name = resource_email.split("@")[0].replace("{{", "").lower()
    for unwanted_char in unwanted_chars:
        resource_name = resource_name.replace(unwanted_char, "_")
    return str(os.path.join(resource_dir, f"{resource_name}.yaml"))


async def generate_domain_group_resource_files(
    exe_message: ExecutionMessage, project: GoogleProject, domain: str
):
    account_group_response_dir = get_response_dir(exe_message, project, domain)

    log.info("Caching Google groups.", project_id=project.project_id, domain=domain)

    groups = await list_groups(domain, project)
    for group in groups:
        group.file_path = os.path.join(
            account_group_response_dir, f"{group.properties.email.split('@')[0]}.yaml"
        )
        group.write()

    log.info(
        "Finished caching Google groups.",
        project_id=project.project_id,
        domain=domain,
        group_count=len(groups),
    )


async def update_or_create_group_template(
    discovered_group_template: GoogleWorkspaceGroupTemplate,
    existing_template_map: dict,
    group_dir: str,
) -> GoogleWorkspaceGroupTemplate:
    discovered_group_template.file_path = get_templated_resource_file_path(
        group_dir,
        discovered_group_template.properties.email,
    )

    return common_create_or_update_template(
        discovered_group_template.file_path,
        existing_template_map,
        discovered_group_template.resource_id,
        GoogleWorkspaceGroupTemplate,
        {},
        discovered_group_template.properties,
        [],
    )


async def collect_project_groups(
    exe_message: ExecutionMessage, config: GoogleWorkspaceConfig
):
    assert exe_message.provider_id
    project = config.get_workspace(exe_message.provider_id)
    log.info("Beginning to retrieve Google groups.", project=project.project_id)

    await asyncio.gather(
        *[
            generate_domain_group_resource_files(exe_message, project, subject.domain)
            for subject in project.subjects
        ]
    )

    log.info("Finished retrieving Google group details", project=project.project_id)


async def generate_group_templates(
    exe_message: ExecutionMessage,
    config: GoogleWorkspaceConfig,
    output_dir: str,
    detect_messages: list = None,
):
    """List all groups in the domain, along with members and
    settings"""

    base_path = os.path.expanduser(output_dir)
    existing_template_map = await get_existing_template_map(
        base_path, GOOGLE_GROUP_TEMPLATE_TYPE
    )
    all_resource_ids = set()

    log.info("Updating and creating Google group templates.")

    for workspace in config.workspaces:
        for subject in workspace.subjects:
            domain = subject.domain
            group_dir = get_group_dir(base_path, domain)

            groups = await exe_message.get_sub_exe_files(
                *get_resource_dir_args(domain),
                "templates",
                file_name_and_extension="**.yaml",
            )
            # Update or create templates
            for group in groups:
                group = GoogleWorkspaceGroupTemplate(file_path="unset", **group)
                group.file_path = group.default_file_path
                resource_template = await update_or_create_group_template(
                    group, existing_template_map, group_dir
                )
                if not resource_template:
                    # Template not updated. Most likely because it's an `enforced` template.
                    continue
                all_resource_ids.add(resource_template.resource_id)

    # Delete templates that no longer exist
    delete_orphaned_templates(list(existing_template_map.values()), all_resource_ids)

    log.info("Finish updating and creating Google group templates.")
