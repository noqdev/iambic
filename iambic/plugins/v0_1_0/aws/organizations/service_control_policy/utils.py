from __future__ import annotations

import asyncio
from itertools import chain

from botocore.exceptions import ClientError
from deepdiff import DeepDiff

from iambic.core import noq_json as json
from iambic.core.context import ExecutionContext
from iambic.core.logger import log
from iambic.core.models import ProposedChange, ProposedChangeType
from iambic.core.utils import NoqSemaphore, aio_wrapper, plugin_apply_wrapper
from iambic.plugins.v0_1_0.aws.models import AWSAccount
from iambic.plugins.v0_1_0.aws.utils import boto_crud_call, paginated_search


async def get_service_control_policy(org_client, policy_id: str) -> dict:
    try:
        response = (
            await boto_crud_call(org_client.describe_policy, PolicyId=policy_id)
        ).get("Policy", {})
        if response:
            response["PolicyDocument"] = json.loads(response["Content"])
            del response["Content"]
    except ClientError as err:
        if err.response["Error"]["Code"] == "NoSuchEntity":
            response = {}
        else:
            raise

    return response


async def delete_service_control_policy(org_client, policy_id: str, log_params: dict):
    try:
        await boto_crud_call(org_client.delete_policy, PolicyId=policy_id)
        log.info("Deleted Service Control Policy", policy_id=policy_id, **log_params)
    except ClientError as err:
        if err.response["Error"]["Code"] == "NoSuchEntity":
            log.info(
                "Service Control Policy not found", policy_id=policy_id, **log_params
            )
        else:
            raise


async def apply_update_service_control_policy(
    org_client,
    policy_id: str,
    template_policy_document: dict,
    existing_policy_document: dict,
    iambic_import_only: bool,
    log_params: dict,
    context: ExecutionContext,
) -> list[ProposedChange]:
    response = []
    if isinstance(existing_policy_document, str):
        existing_policy_document = json.loads(existing_policy_document)
    policy_drift = await aio_wrapper(
        DeepDiff,
        existing_policy_document,
        template_policy_document,
        ignore_order=True,
        report_repetition=True,
    )

    if policy_drift:
        policy_drift = json.loads(policy_drift.to_json())
        log_str = "Changes to the PolicyDocument discovered."
        proposed_changes = [
            ProposedChange(
                change_type=ProposedChangeType.UPDATE,
                attribute="policy_document",
                change_summary=policy_drift,
                current_value=existing_policy_document,
                new_value=template_policy_document,
            )
        ]
        response.extend(proposed_changes)

        if not iambic_import_only:
            if context.execute:
                log_str = f"{log_str} Updating PolicyDocument..."
                await boto_crud_call(
                    org_client.update_policy,
                    PolicyId=policy_id,
                    Content=json.dumps(template_policy_document),
                )
                log.info(log_str, **log_params)

        log.info(log_str, **log_params)
    return response


async def apply_service_control_policy_tags(
    org_client,
    policy_id: str,
    template_tags: list[dict],
    existing_tags: list[dict],
    iambic_import_only: bool,
    log_params: dict,
    context: ExecutionContext,
) -> list[ProposedChange]:
    existing_tag_map = {tag["Key"]: tag.get("Value") for tag in existing_tags}
    template_tag_map = {tag["Key"]: tag.get("Value") for tag in template_tags}
    tags_to_apply = [
        tag
        for tag in template_tags
        if tag.get("Value") != existing_tag_map.get(tag["Key"])
    ]
    tasks = []
    response = []

    if tags_to_remove := [
        tag["Key"] for tag in existing_tags if not template_tag_map.get(tag["Key"])
    ]:
        log_str = "Stale tags discovered."
        proposed_changes = [
            ProposedChange(
                change_type=ProposedChangeType.DETACH,
                attribute="tags",
                change_summary={"TagKeys": tags_to_remove},
            )
        ]
        response.extend(proposed_changes)

        if not iambic_import_only:
            log_str = f"{log_str} Removing tags..."
            apply_awaitable = boto_crud_call(
                org_client.untag_resource,
                ResourceId=policy_id,
                TagKeys=tags_to_remove,
            )
            tasks.append(plugin_apply_wrapper(apply_awaitable, proposed_changes))
        log.info(log_str, tags=tags_to_remove, **log_params)

    if tags_to_apply:
        log_str = "New tags discovered in AWS."
        proposed_changes = [
            ProposedChange(
                change_type=ProposedChangeType.ATTACH,
                attribute="tags",
                new_value=tag,
            )
            for tag in tags_to_apply
        ]
        response.extend(proposed_changes)
        if context.execute:
            log_str = f"{log_str} Adding tags..."
            apply_awaitable = boto_crud_call(
                org_client.tag_resource, ResourceId=policy_id, Tags=tags_to_apply
            )
            tasks.append(plugin_apply_wrapper(apply_awaitable, proposed_changes))
        log.info(log_str, tags=tags_to_apply, **log_params)

    if tasks:
        results: list[list[ProposedChange]] = await asyncio.gather(*tasks)
        return list(chain.from_iterable(results))
    else:
        return response
