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
from iambic.plugins.v0_1_0.okta.group_rule.models import (
    OKTA_GROUP_RULE_TEMPLATE_TYPE,
    GroupRuleProperties,
    OktaGroupRuleTemplate
)
from iambic.plugins.v0_1_0.okta.group_rule.utils import list_all_group_rules

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.okta.iambic_plugin import OktaConfig

def get_resource_dir_args() -> list:
    return ["group_rule"]

def get_response_dir(exe_message: ExecutionMessage) -> str:
    return exe_message.get_directory(*get_resource_dir_args(), "templates") 

async def collect_org_group_rules(exe_message: ExecutionMessage, config: OktaConfig):
    assert exe_message.provider_id
    base_path = get_response_dir(exe_message)
    okta_organization = config.get_organization(exe_message.provider_id)
    log.info("Beginning to retrieve Okta group rules.", organization=exe_message.provider_id)

    rules = await list_all_group_rules(okta_organization)
    for rule in rules:
        rule_tmpl = OktaGroupRuleTemplate(
            file_path="unset",
            idp_name=rule.idp_name,
            properties=GroupRuleProperties(
                status=rule.status,
                rule_id=rule.rule_id,
                name=rule.name,
                conditions=rule.conditions,
                actions=rule.actions
            ),
        )
        rule_tmpl.file_path = os.path.join(base_path, f"{rule.name}.yaml")
        rule_tmpl.write()

    log.info(
        "Finished retrieving Okta group rules.",
        okta_org=exe_message.provider_id,
        group_rules_count=len(rules),
    )


async def collect_org_group_rules(exe_message: ExecutionMessage, config: OktaConfig):
    assert exe_message.provider_id
    base_path = get_response_dir(exe_message)
    okta_organization = config.get_organization(exe_message.provider_id)
    log.info("Beginning to retrieve Okta groups.", organization=exe_message.provider_id)

    rules = await list_all_group_rules(okta_organization)
    for rule in rules:

        okta_group = OktaGroupRuleTemplate(
            file_path="unset",
            idp_name=rule.idp_name,
            properties=GroupRuleProperties(
                group_id=rule.group_id,
                name=rule.name,
                conditions=rule.conditions,
                actions=rule.actions,
                description=rule.description,
            ),
        )
        okta_group.file_path = os.path.join(base_path, f"{rule.name}.yaml")
        okta_group.write()

    log.info(
        "Finished retrieving Okta groups.",
        okta_org=exe_message.provider_id,
        group_count=len(rules),
    )

async def generate_rule_templates(
    config: OktaConfig,
    exe_message: ExecutionMessage,
    output_dir: str,
    detect_messages: list = None,
):
    base_path = os.path.expanduser(output_dir)
    existing_template_map = await get_existing_template_map(
        base_path,
        OKTA_GROUP_RULE_TEMPLATE_TYPE,
        config.template_map,
    )
    all_resource_ids = set()

    log.info("Updating and creating Okta group rules templates.")

    rules = await exe_message.get_sub_exe_files(
        *get_resource_dir_args(), "templates", file_name_and_extension="**.yaml"
    )
    # Update or create templates
    for rule in rules:
        group = OktaGroupRuleTemplate(file_path="unset", **group)
        group.set_default_file_path(output_dir)
        resource_template = await update_or_create_rule_template(
            group, existing_template_map
        )
        if not resource_template:
            # Template not updated. Most likely because it's an `enforced` template.
            continue
        all_resource_ids.add(resource_template.resource_id)

    # Delete templates that no longer exist
    delete_orphaned_templates(list(existing_template_map.values()), all_resource_ids)

    log.info("Finish updating and creating Okta group templates.")



async def generate_rule_templates(
    config: OktaConfig,
    exe_message: ExecutionMessage,
    output_dir: str,
    detect_messages: list = None,
):
    """List all groups in the domain, along with members and settings"""
    base_path = os.path.expanduser(output_dir)
    existing_template_map = await get_existing_template_map(
        base_path,
        OKTA_GROUP_RULE_TEMPLATE_TYPE,
        config.template_map,
    )
    all_resource_ids = set()

    log.info("Updating and creating Okta rule templates.")

    rules = await exe_message.get_sub_exe_files(
        *get_resource_dir_args(), "templates", file_name_and_extension="**.yaml"
    )
    # Update or create templates
    for rule in rules:
        rule = OktaGroupRuleTemplate(file_path="unset", **rule)
        rule.set_default_file_path(output_dir)
        resource_template = await update_or_create_rule_template(
            rule, existing_template_map
        )
        if not resource_template:
            # Template not updated. Most likely because it's an `enforced` template.
            continue
        all_resource_ids.add(resource_template.resource_id)

    # Delete templates that no longer exist
    delete_orphaned_templates(list(existing_template_map.values()), all_resource_ids)

    log.info("Finish updating and creating Okta group templates.")

async def update_or_create_rule_template(
    discovered_template: OktaGroupRuleTemplate, existing_template_map: dict
) -> OktaGroupRuleTemplate:
    return create_or_update_template(
        discovered_template.file_path,
        existing_template_map,
        discovered_template.resource_id,
        OktaGroupRuleTemplate,
        {"idp_name": discovered_template.idp_name},
        discovered_template.properties,
        [],
    )