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
from iambic.plugins.v0_1_0.google_workspace.user.models import (
    GOOGLE_USER_TEMPLATE_TYPE,
    GoogleWorkspaceUserTemplate,
)
from iambic.plugins.v0_1_0.google_workspace.user.utils import list_users

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.google_workspace.iambic_plugin import (
        GoogleProject,
        GoogleWorkspaceConfig,
    )


def get_resource_dir_args(domain: str) -> list:
    return ["user", domain]


def get_response_dir(
    exe_message: ExecutionMessage, google_project: GoogleProject, domain: str
) -> str:
    dir_args = get_resource_dir_args(domain)
    dir_args.append("templates")
    if exe_message.provider_id:
        return exe_message.get_directory(*dir_args)
    else:
        return exe_message.get_directory(google_project.project_id, *dir_args)


def get_user_dir(
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


async def generate_domain_user_resource_files(
    exe_message: ExecutionMessage, project: GoogleProject, domain: str
):
    account_user_response_dir = get_response_dir(exe_message, project, domain)

    log.info("Caching Google users.", project_id=project.project_id, domain=domain)

    users = await list_users(domain, project)
    for user in users:
        user.file_path = os.path.join(
            account_user_response_dir,
            f"{user.properties.primary_email.split('@')[0]}.yaml",
        )
        user.write()

    log.info(
        "Finished caching Google users.",
        project_id=project.project_id,
        domain=domain,
        user_count=len(users),
    )


async def update_or_create_user_template(
    discovered_user_template: GoogleWorkspaceUserTemplate,
    existing_template_map: dict,
    user_dir: str,
) -> GoogleWorkspaceUserTemplate:
    discovered_user_template.file_path = get_templated_resource_file_path(
        user_dir,
        discovered_user_template.properties.primary_email,
    )

    return common_create_or_update_template(
        discovered_user_template.file_path,
        existing_template_map,
        discovered_user_template.resource_id,
        GoogleWorkspaceUserTemplate,
        {},
        discovered_user_template.properties,
        [],
    )


async def collect_project_users(
    exe_message: ExecutionMessage, config: GoogleWorkspaceConfig
):
    assert exe_message.provider_id
    project = config.get_workspace(exe_message.provider_id)
    log.info("Beginning to retrieve Google users.", project=project.project_id)

    await asyncio.gather(
        *[
            generate_domain_user_resource_files(exe_message, project, subject.domain)
            for subject in project.subjects
        ]
    )

    log.info("Finished retrieving Google user details", project=project.project_id)


async def generate_user_templates(
    exe_message: ExecutionMessage,
    config: GoogleWorkspaceConfig,
    output_dir: str,
    detect_messages: list = None,
):
    """List all users in the domain"""

    base_path = os.path.expanduser(output_dir)
    existing_template_map = await get_existing_template_map(
        base_path,
        GOOGLE_USER_TEMPLATE_TYPE,
        config.template_map,
    )
    all_resource_ids = set()

    log.info("Updating and creating Google user templates.")

    for workspace in config.workspaces:
        for subject in workspace.subjects:
            domain = subject.domain
            user_dir = get_user_dir(base_path, domain)

            users = await exe_message.get_sub_exe_files(
                *get_resource_dir_args(domain),
                "templates",
                file_name_and_extension="**.yaml",
            )
            # Update or create templates
            for user in users:
                user = GoogleWorkspaceUserTemplate(file_path="unset", **user)
                user.file_path = user.default_file_path
                resource_template = await update_or_create_user_template(
                    user, existing_template_map, user_dir
                )
                if not resource_template:
                    # Template not updated. Most likely because it's an `enforced` template.
                    continue
                all_resource_ids.add(resource_template.resource_id)

    # Delete templates that no longer exist
    delete_orphaned_templates(list(existing_template_map.values()), all_resource_ids)

    log.info("Finish updating and creating Google user templates.")
