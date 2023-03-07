from __future__ import annotations

import os
from typing import TYPE_CHECKING

from iambic.core.logger import log
from iambic.core.template_generation import (
    create_or_update_template as common_create_or_update_template,
)
from iambic.core.template_generation import (
    delete_orphaned_templates,
    get_existing_template_map,
)
from iambic.plugins.v0_1_0.okta.group.utils import list_all_users
from iambic.plugins.v0_1_0.okta.models import User
from iambic.plugins.v0_1_0.okta.user.models import (
    OKTA_USER_TEMPLATE_TYPE,
    OktaUserTemplate,
    OktaUserTemplateProperties,
)

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.okta.iambic_plugin import OktaConfig, OktaOrganization


def get_user_dir(base_dir: str, idp_name: str) -> str:
    return str(os.path.join(base_dir, "resources", "okta", idp_name, "users"))


def get_templated_resource_file_path(
    resource_dir: str,
    resource_name: str,
) -> str:
    unwanted_chars = ["}}_", "}}", ".", "-", " "]
    resource_name = resource_name.replace("{{", "").lower()
    for unwanted_char in unwanted_chars:
        resource_name = resource_name.replace(unwanted_char, "_")

    return str(os.path.join(resource_dir, f"{resource_name}.yaml"))


async def update_or_create_user_template(
    user: User, existing_template_map: dict, user_dir: str
) -> User:
    """
    Update or create an OktaUserTemplate object from the provided User object.

    Args:
        user (User): The User object to generate the template from.
        existing_template_map (dict): Existing IAMbic Okta user templates.
        user_dir (str): The default directory to store the template in.
    """
    properties = OktaUserTemplateProperties(
        username=user.username,
        idp_name=user.idp_name,
        user_id=user.user_id,
        status=user.status.value,
        profile=user.profile,
    )

    file_path = get_templated_resource_file_path(user_dir, user.username)
    OktaUserTemplate.update_forward_refs()

    return common_create_or_update_template(
        file_path,
        existing_template_map,
        user.user_id,
        OktaUserTemplate,
        {},
        properties,
        [],
    )


async def generate_user_templates(
    config: OktaConfig, output_dir: str, okta_organization: OktaOrganization
):
    users = await list_all_users(okta_organization)
    log.info(
        f"Found {len(users)} users in the `{okta_organization.idp_name}` Okta organization"
    )
    base_path = os.path.expanduser(output_dir)
    existing_template_map = await get_existing_template_map(
        base_path, OKTA_USER_TEMPLATE_TYPE
    )
    user_dir = get_user_dir(base_path, okta_organization.idp_name)

    all_resource_ids = set()
    for okta_user in users:
        resource_template = await update_or_create_user_template(
            okta_user, existing_template_map, user_dir
        )
        all_resource_ids.add(resource_template.resource_id)

    delete_orphaned_templates(list(existing_template_map.values()), all_resource_ids)
