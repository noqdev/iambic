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
from iambic.plugins.v0_1_0.okta.app.models import (
    OKTA_APP_TEMPLATE_TYPE,
    OktaAppTemplate,
    get_app_template,
)
from iambic.plugins.v0_1_0.okta.app.utils import list_all_apps

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.okta.iambic_plugin import OktaConfig


def get_resource_dir_args() -> list:
    return ["app"]


def get_response_dir(exe_message: ExecutionMessage) -> str:
    return exe_message.get_directory(*get_resource_dir_args(), "templates")


async def update_or_create_app_template(
    discovered_template: OktaAppTemplate, existing_template_map: dict
) -> OktaAppTemplate:
    return create_or_update_template(
        discovered_template.file_path,
        existing_template_map,
        discovered_template.resource_id,
        OktaAppTemplate,
        {"idp_name": discovered_template.idp_name},
        discovered_template.properties,
        [],
    )


async def collect_org_apps(exe_message: ExecutionMessage, config: OktaConfig):
    assert exe_message.provider_id
    base_path = get_response_dir(exe_message)
    okta_organization = config.get_organization(exe_message.provider_id)
    log.info("Beginning to retrieve Okta apps.", organization=exe_message.provider_id)

    apps = await list_all_apps(okta_organization)
    for okta_app in apps:
        app = await get_app_template(okta_app)
        app.file_path = os.path.join(base_path, f"{okta_app.name}.yaml")
        app.write()

    log.info(
        "Finished retrieving Okta apps.",
        okta_org=exe_message.provider_id,
        app_count=len(apps),
    )


async def generate_app_templates(
    exe_message: ExecutionMessage, output_dir: str, detect_messages: list = None
):
    """List all apps in the domain, along with members and settings"""
    base_path = os.path.expanduser(output_dir)
    existing_template_map = await get_existing_template_map(
        base_path, OKTA_APP_TEMPLATE_TYPE
    )
    all_resource_ids = set()

    log.info("Updating and creating Okta app templates.")

    apps = await exe_message.get_sub_exe_files(
        *get_resource_dir_args(), "templates", file_name_and_extension="**.yaml"
    )
    # Update or create templates
    for app in apps:
        app = OktaAppTemplate(file_path="unset", **app)
        app.set_default_file_path(output_dir)
        resource_template = await update_or_create_app_template(
            app, existing_template_map
        )
        if not resource_template:
            # Template not updated. Most likely because it's an `enforced` template.
            continue
        all_resource_ids.add(resource_template.resource_id)

    # Delete templates that no longer exist
    delete_orphaned_templates(list(existing_template_map.values()), all_resource_ids)

    log.info("Finish updating and creating Okta app templates.")
