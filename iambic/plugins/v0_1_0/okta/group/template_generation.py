from __future__ import annotations

import os
from typing import TYPE_CHECKING

from iambic.core import noq_json as json
from iambic.core.logger import log
from iambic.core.models import ExecutionMessage
from iambic.core.template_generation import (
    create_or_update_template,
    delete_orphaned_templates,
    get_existing_template_map,
)
from iambic.plugins.v0_1_0.okta.group.models import (
    OKTA_GROUP_TEMPLATE_TYPE,
    GroupProperties,
    OktaGroupTemplate,
)
from iambic.plugins.v0_1_0.okta.group.utils import list_all_groups

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.okta.iambic_plugin import OktaConfig


def get_resource_dir_args() -> list:
    return ["group"]


def get_response_dir(exe_message: ExecutionMessage) -> str:
    return exe_message.get_directory(*get_resource_dir_args(), "templates")


async def update_or_create_group_template(
    discovered_template: OktaGroupTemplate, existing_template_map: dict
) -> OktaGroupTemplate:
    return create_or_update_template(
        discovered_template.file_path,
        existing_template_map,
        discovered_template.resource_id,
        OktaGroupTemplate,
        {"idp_name": discovered_template.idp_name},
        discovered_template.properties,
        [],
    )


async def collect_org_groups(exe_message: ExecutionMessage, config: OktaConfig):
    assert exe_message.provider_id
    base_path = get_response_dir(exe_message)
    okta_organization = config.get_organization(exe_message.provider_id)
    log.info("Beginning to retrieve Okta groups.", organization=exe_message.provider_id)

    groups = await list_all_groups(okta_organization)
    for group in groups:
        okta_group = OktaGroupTemplate(
            file_path="unset",
            idp_name=group.idp_name,
            properties=GroupProperties(
                group_id=group.group_id,
                name=group.name,
                description=group.description,
                members=[json.loads(m.json()) for m in group.members],
            ),
        )
        okta_group.file_path = os.path.join(base_path, f"{group.name}.yaml")
        okta_group.write()

    log.info(
        "Finished retrieving Okta groups.",
        okta_org=exe_message.provider_id,
        group_count=len(groups),
    )


async def generate_group_templates(
    exe_message: ExecutionMessage, output_dir: str, detect_messages: list = None
):
    """List all groups in the domain, along with members and settings"""
    base_path = os.path.expanduser(output_dir)
    existing_template_map = await get_existing_template_map(
        base_path, OKTA_GROUP_TEMPLATE_TYPE
    )
    all_resource_ids = set()

    log.info("Updating and creating Okta group templates.")

    groups = await exe_message.get_sub_exe_files(
        *get_resource_dir_args(), "templates", file_name_and_extension="**.yaml"
    )
    # Update or create templates
    for group in groups:
        group = OktaGroupTemplate(file_path="unset", **group)
        group.set_default_file_path(output_dir)
        resource_template = await update_or_create_group_template(
            group, existing_template_map
        )
        if not resource_template:
            # Template not updated. Most likely because it's an `enforced` template.
            continue
        all_resource_ids.add(resource_template.resource_id)

    # Delete templates that no longer exist
    delete_orphaned_templates(list(existing_template_map.values()), all_resource_ids)

    log.info("Finish updating and creating Okta group templates.")
