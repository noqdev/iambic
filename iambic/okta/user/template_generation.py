from __future__ import annotations

import os

from iambic.core.logger import log
from iambic.core.template_generation import (
    create_or_update_template as common_create_or_update_template,
)
from iambic.core.template_generation import get_existing_template_map
from iambic.okta.group.utils import list_all_users
from iambic.okta.models import User
from iambic.okta.user.models import (
    OKTA_USER_TEMPLATE_TYPE,
    OktaUserTemplate,
    OktaUserTemplateProperties,
)


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
):
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

    common_create_or_update_template(
        file_path,
        existing_template_map,
        user.user_id,
        OktaUserTemplate,
        {},
        properties,
        [],
    )


async def generate_user_templates(config, output_dir, okta_organization):
    users = await list_all_users(okta_organization)
    log.info(
        f"Found {len(users)} users in the `{okta_organization.idp_name}` Okta organization"
    )
    base_path = os.path.expanduser(output_dir)
    existing_template_map = await get_existing_template_map(
        base_path, OKTA_USER_TEMPLATE_TYPE
    )
    user_dir = get_user_dir(base_path, okta_organization.idp_name)

    for okta_user in users:
        await update_or_create_user_template(okta_user, existing_template_map, user_dir)

    discovered_user_ids = [user.user_id for user in users]
    for user_id, template in existing_template_map.items():
        if user_id not in discovered_user_ids:
            template.delete()
