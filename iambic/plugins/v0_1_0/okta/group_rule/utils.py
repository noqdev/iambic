from __future__ import annotations

import asyncio
import functools
from typing import TYPE_CHECKING, List, Optional

import okta.models as models
from okta.models.user_status import UserStatus as OktaUserStatus

from iambic.core.context import ctx
from iambic.core.logger import log
from iambic.core.models import ProposedChange, ProposedChangeType
from iambic.core.utils import GlobalRetryController
from iambic.plugins.v0_1_0.okta.models import GroupRule
from iambic.plugins.v0_1_0.okta.utils import generate_user_profile, handle_okta_fn

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.okta.group.models import UserSimple
    from iambic.plugins.v0_1_0.okta.iambic_plugin import OktaOrganization


async def list_all_group_rules(okta_organization: OktaOrganization) -> List[GroupRule]:
    client = await okta_organization.get_okta_client()
    async with GlobalRetryController(
        fn_identifier="okta.list_group_rules"
    ) as retry_controller:
        fn = functools.partial(client.list_groups)
        rules, resp, err = await retry_controller(handle_okta_fn, fn)
        if err:
            raise Exception(f"Error listing group rules: {str(err)}")

    while resp.has_next():
        async with GlobalRetryController(
            fn_identifier="okta.list_groups"
        ) as retry_controller:
            next_rules, err = await retry_controller(handle_okta_fn, resp.next)
        if err:
            log.error("Error encountered when listing groups", error=str(err))
            raise Exception(f"Error listing groups: {str(err)}")
        rules.append(next_rules)

    if not rules:
        log.info(
            "No rules found in Okta Organization",
            okta_organization=okta_organization.idp_name,
        )
        return []
    rules = []
    for rule_raw in rules:
        rule = GroupRule(
            idp_name=okta_organization.idp_name,
            name=rule_raw.profile.name,
            rule_id=rule_raw.id,
            conditions=str(rule_raw.conditions),
            actions=str(rule_raw.actions),
            extra=dict(
                created=rule_raw.created,
            ),
        )
        rules.append(rule)
    return rules


async def get_group_rule(
    rule_id: str, rule_name: str, okta_organization: OktaOrganization
) -> Optional[GroupRule]:
    client = await okta_organization.get_okta_client()
    rule = None
    if rule_id:
        async with GlobalRetryController(
            fn_identifier="okta.get_group"
        ) as retry_controller:
            fn = functools.partial(client.get_group_rule, rule_id)
            rules, resp, err = await retry_controller(handle_okta_fn, fn)
    if not rule:
        # Try to get group by name
        async with GlobalRetryController(
            fn_identifier="okta.list_group_rules"
        ) as retry_controller:
            fn = functools.partial(client.list_group_rules, query_params={"q": rule_name})
            groups, resp, err = await retry_controller(handle_okta_fn, fn)
        if err:
            log.error(
                "Error encountered when getting group by name",
                rule_id=rule_id,
                rule_name=rule_name,
                error=str(err),
            )
            return None
        matching_rule = None
        for matching_rule in rules:
            if matching_rule.profile.name == rule_name:
                group = matching_rule
                break

        if not rule:
            return None
    if err:
        log.error(
            "Error encountered when getting group rule",
            group_id=rule_id,
            group_name=rule_name,
            error=str(err),
        )
        return None

    rule = GroupRule(
        idp_name=okta_organization.idp_name,
        name=rule.profile.name,
        rule_id=rule.id,
        conditions=str(rule.conditions),
        actions=str(rule.actions)
    )
    
    return rule


async def create_rule(
    rule_name: str,
    idp_name: str,
    conditions: str,
    actions: str,
    okta_organization: OktaOrganization,
) -> Optional[GroupRule]:
    client = await okta_organization.get_okta_client()

    group_profile = models.GroupProfile(
        {
            "name": group_name,
            "description": description,
        }
    )

    # Create the group
    group_model = models.GroupRule({"profile": group_profile})
    if ctx.execute:
        async with GlobalRetryController(
            fn_identifier="okta.create_group"
        ) as retry_controller:
            fn = functools.partial(client.create_group, group_model)
            group, resp, err = await retry_controller(handle_okta_fn, fn)
        if err:
            raise Exception("Error creating group")
        rule = GroupRule(
            idp_name=idp_name,
            name=rule_name,
            group_id=group.id,
            
        )
        return rule
    return None


async def update_rule(
    group: GroupRule,
    new_name: str,
    okta_organization: OktaOrganization,
    log_params: dict[str, str],
) -> List[ProposedChange]:

    response: list[ProposedChange] = []
    if group.name == new_name:
        return response
    response.append(
        ProposedChange(
            change_type=ProposedChangeType.UPDATE,
            resource_id=group.group_id,
            resource_type=group.resource_type,
            attribute="group_name",
            current_value=group.name,
            new_value=new_name,
        )
    )
    group_model = models.GrouRulep(
        {
            "profile": models.GroupProfile(
                {
                    "name": new_name,
                    "description": group.description,
                }
            )
        }
    )
    if ctx.execute:
        client = await okta_organization.get_okta_client()
        async with GlobalRetryController(
            fn_identifier="okta.update_group"
        ) as retry_controller:
            fn = functools.partial(client.update_group, group.group_id, group_model)
            updated_group, resp, err = await retry_controller(handle_okta_fn, fn)
        if err:
            raise Exception("Error updating group")
        GroupRule(
            idp_name=okta_organization.idp_name,
            name=updated_group.profile.name,
            description=updated_group.profile.description,
            group_id=updated_group.id,
            attributes=dict(),
            extra=dict(
                created=updated_group.created,
            ),
        )
    return response


async def update_rule(
    group: GroupRule,
    okta_organization: OktaOrganization
) -> List[ProposedChange]:

    client = await okta_organization.get_okta_client()
    response = []

    if ctx.execute:
        async with GlobalRetryController(
            fn_identifier="okta.deactivate_rule"
        ) as retry_controller:
            fn = functools.partial(client.get_user, user)
            user_okta, _, err = await retry_controller(handle_okta_fn, fn)
        if err:
            log.error("Error retrieving user", user=user, **log_params)
            continue
            async with GlobalRetryController(
                fn_identifier="okta.remove_user_from_group"
            ) as retry_controller:
                fn = functools.partial(
                    client.remove_user_from_group,
                    group.group_id,
                    user_okta.id,
                )
                _, err = await retry_controller(handle_okta_fn, fn)
            if err:
                log.error(
                    "Error removing user from group",
                    user=user,
                    group=group.name,
                    **log_params,
                )
                continue

        for user in users_to_add:
            async with GlobalRetryController(
                fn_identifier="okta.get_user"
            ) as retry_controller:
                fn = functools.partial(client.get_user, user)
                user_okta, _, err = await retry_controller(handle_okta_fn, fn)
            if err:
                log.error("Error retrieving user", user=user, **log_params)
                continue
            async with GlobalRetryController(
                fn_identifier="okta.add_user_to_group"
            ) as retry_controller:
                fn = functools.partial(
                    client.add_user_to_group, group.group_id, user_okta.id
                )
                _, err = await retry_controller(handle_okta_fn, fn)
            if err:
                log.error(
                    "Error adding user to group",
                    user=user,
                    group=group.name,
                    **log_params,
                )
                continue
    return response


async def maybe_delete_group(
    delete: bool,
    rule: GroupRule,
    okta_organization: OktaOrganization,
    log_params: dict[str, str],
) -> List[ProposedChange]:

    response: list[ProposedChange] = []
    client = await okta_organization.get_okta_client()
    if not delete:
        return response
    response.append(
        ProposedChange(
            change_type=ProposedChangeType.DELETE,
            resource_id=rule.group_id,
            resource_type=rule.resource_type,
            attribute="group_rule",
            change_summary={"group_rule": rule.name},
            current_value=rule.name,
            new_value=None,
        )
    )
    if ctx.execute:
        async with GlobalRetryController(
            fn_identifier="okta.delete_group"
        ) as retry_controller:
            fn = functools.partial(client.delete_group, rule.rule_id)
            _, err = await retry_controller(handle_okta_fn, fn)
        if err:
            raise Exception("Error deleting group")
    return response
