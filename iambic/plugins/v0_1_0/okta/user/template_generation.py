from __future__ import annotations

import os
from typing import TYPE_CHECKING

from iambic.core.logger import log
from iambic.core.models import ExecutionMessage
from iambic.core.template_generation import (
    create_or_update_template,
    delete_orphaned_templates,
    get_existing_template_map,
)
from iambic.plugins.v0_1_0.okta.group.utils import list_all_users
from iambic.plugins.v0_1_0.okta.user.models import (
    OKTA_USER_TEMPLATE_TYPE,
    OktaUserTemplate,
    UserProperties,
)

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.okta.iambic_plugin import OktaConfig


def get_resource_dir_args() -> list:
    return ["user"]


def get_response_dir(exe_message: ExecutionMessage) -> str:
    return exe_message.get_directory(*get_resource_dir_args(), "templates")


async def update_or_create_user_template(
    discovered_template: OktaUserTemplate, existing_template_map: dict
) -> OktaUserTemplate:
    return create_or_update_template(
        discovered_template.file_path,
        existing_template_map,
        discovered_template.resource_id,
        OktaUserTemplate,
        {"idp_name": discovered_template.idp_name},
        discovered_template.properties,
        [],
    )


async def collect_org_users(exe_message: ExecutionMessage, config: OktaConfig):
    assert exe_message.provider_id
    base_path = get_response_dir(exe_message)
    okta_organization = config.get_organization(exe_message.provider_id)
    log.info("Beginning to retrieve Okta users.", organization=exe_message.provider_id)

    users = await list_all_users(okta_organization)
    for user in users:
        okta_user = OktaUserTemplate(
            file_path="unset",
            idp_name=user.idp_name,
            properties=UserProperties(
                username=user.username,
                user_id=user.user_id,
                status=user.status.value,
                profile=user.profile,
            ),
        )
        okta_user.file_path = os.path.join(base_path, f"{user.username}.yaml")
        okta_user.write()

    log.info(
        "Finished retrieving Okta users.",
        okta_org=exe_message.provider_id,
        user_count=len(users),
    )


async def generate_user_templates(
    exe_message: ExecutionMessage, output_dir: str, detect_messages: list = None
):
    """List all users in the domain, along with members and settings"""
    base_path = os.path.expanduser(output_dir)
    existing_template_map = await get_existing_template_map(
        base_path, OKTA_USER_TEMPLATE_TYPE
    )
    all_resource_ids = set()

    log.info("Updating and creating Okta user templates.")

    users = await exe_message.get_sub_exe_files(
        *get_resource_dir_args(), "templates", file_name_and_extension="**.yaml"
    )
    # Update or create templates
    for user in users:
        user = OktaUserTemplate(file_path="unset", **user)
        user.set_default_file_path(output_dir)
        resource_template = await update_or_create_user_template(
            user, existing_template_map
        )
        if not resource_template:
            # Template not updated. Most likely because it's an `enforced` template.
            continue
        all_resource_ids.add(resource_template.resource_id)

    # Delete templates that no longer exist
    delete_orphaned_templates(list(existing_template_map.values()), all_resource_ids)

    log.info("Finish updating and creating Okta user templates.")
