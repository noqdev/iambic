from __future__ import annotations

import asyncio
from itertools import chain

from botocore.exceptions import ClientError
from deepdiff import DeepDiff

from iambic.core import noq_json as json
from iambic.core.context import ctx
from iambic.core.logger import log
from iambic.core.models import ProposedChange, ProposedChangeType
from iambic.core.utils import NoqSemaphore, aio_wrapper, plugin_apply_wrapper
from iambic.plugins.v0_1_0.aws.models import AWSAccount
from iambic.plugins.v0_1_0.aws.utils import boto_crud_call, paginated_search


async def list_managed_policy_versions(iam_client, policy_arn: str) -> list[dict]:
    return (
        await boto_crud_call(iam_client.list_policy_versions, PolicyArn=policy_arn)
    ).get("Versions", [])


async def list_managed_policy_tags(iam_client, policy_arn: str) -> list[dict]:
    return await paginated_search(
        iam_client.list_policy_tags, "Tags", PolicyArn=policy_arn
    )


async def get_managed_policy_version_doc(
    iam_client, policy_arn: str, version_id: str, **kwargs
) -> dict:
    return (
        (
            await boto_crud_call(
                iam_client.get_policy_version,
                PolicyArn=policy_arn,
                VersionId=version_id,
            )
        )
        .get("PolicyVersion", {})
        .get("Document", {})
    )


async def get_managed_policy_attachments(iam_client, policy_arn: str):
    """
    Get a list of all entities that have the managed policy attached.

    return:
        {
            'PolicyGroups': [{'GroupName': 'string', 'GroupId': 'string'}],
            'PolicyUsers': [{'UserName': 'string', 'UserId': 'string'}],
            'PolicyRoles': [{'RoleName': 'string', 'RoleId': 'string'}]
        }
    """
    return await paginated_search(
        iam_client.list_entities_for_policy,
        response_keys=["PolicyGroups", "PolicyRoles", "PolicyUsers"],
        retain_key=True,
        PolicyArn=policy_arn,
    )


async def get_managed_policy(iam_client, policy_arn: str, **kwargs) -> dict:
    try:
        response = (
            await boto_crud_call(iam_client.get_policy, PolicyArn=policy_arn)
        ).get("Policy", {})
        if response:
            response["PolicyDocument"] = await get_managed_policy_version_doc(
                iam_client, policy_arn, response.pop("DefaultVersionId")
            )
    except ClientError as err:
        if err.response["Error"]["Code"] == "NoSuchEntity":
            response = {}
        else:
            raise

    return response


def get_oldest_policy_version_id(policy_versions: list[dict]) -> str:
    policy_versions = sorted(policy_versions, key=lambda version: version["CreateDate"])
    if not policy_versions[0]["IsDefaultVersion"]:
        return policy_versions[0]["VersionId"]
    elif len(policy_versions) > 1:
        return policy_versions[1]["VersionId"]


async def list_managed_policies(
    iam_client,
    scope: str = "Local",
    only_attached: bool = False,
    path_prefix: str = "/",
    policy_usage_filter: str = None,
):
    get_managed_policy_semaphore = NoqSemaphore(get_managed_policy, 50)
    list_policy_kwargs = dict(
        Scope=scope,
        OnlyAttached=only_attached,
        PathPrefix=path_prefix,
    )
    if policy_usage_filter:
        list_policy_kwargs["PolicyUsageFilter"] = policy_usage_filter

    managed_policies = await paginated_search(
        iam_client.list_policies, response_key="Policies", **list_policy_kwargs
    )
    return await get_managed_policy_semaphore.process(
        [
            {"iam_client": iam_client, "policy_arn": policy["Arn"]}
            for policy in managed_policies
        ]
    )


async def delete_managed_policy(iam_client, policy_arn: str, log_params: dict):
    policy_attachments = await get_managed_policy_attachments(iam_client, policy_arn)
    policy_versions = await list_managed_policy_versions(iam_client, policy_arn)
    tasks = []

    for detachment_type in ["User", "Role", "Group"]:
        for entity in policy_attachments[f"Policy{detachment_type}s"]:
            tasks.append(
                boto_crud_call(
                    getattr(iam_client, f"detach_{detachment_type.lower()}_policy"),
                    PolicyArn=policy_arn,
                    **{f"{detachment_type}Name": entity[f"{detachment_type}Name"]},
                )
            )

    if len(policy_versions) > 1:
        for version in policy_versions:
            if version["IsDefaultVersion"]:
                continue

            tasks.append(
                boto_crud_call(
                    iam_client.delete_policy_version,
                    PolicyArn=policy_arn,
                    VersionId=version["VersionId"],
                )
            )

    log.debug(
        "Detaching managed policy from resources.",
        policy_arn=policy_arn,
        **log_params,
    )
    await asyncio.gather(*tasks)
    await boto_crud_call(iam_client.delete_policy, PolicyArn=policy_arn)


async def apply_update_managed_policy(
    iam_client,
    policy_arn: str,
    template_policy_document: dict,
    existing_policy_document: dict,
    log_params: dict,
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
    # DeepDiff will return type changes as actual type functions and not strings,
    # and this will cause json serialization to fail later on when we process
    # the proposed changes. We force type changes to strings here.

    if policy_drift:
        policy_drift = json.loads(policy_drift.to_json())
        log_str = "Changes to the PolicyDocument discovered."
        proposed_changes = [
            ProposedChange(
                change_type=ProposedChangeType.UPDATE,
                attribute="policy_document",
                change_summary=policy_drift,
                resource_type="aws:policy_document",
                resource_id=policy_arn,
                current_value=existing_policy_document,
                new_value=template_policy_document,
            )
        ]
        response.extend(proposed_changes)

        if ctx.execute:
            apply_awaitable = new_policy_version(
                iam_client,
                policy_arn,
                template_policy_document,
                policy_drift,
                log_str,
                log_params,
            )
            return await plugin_apply_wrapper(apply_awaitable, proposed_changes)

        log.debug(log_str, **log_params)
    return response


async def new_policy_version(
    iam_client, policy_arn, template_policy_document, policy_drift, log_str, log_params
):
    if policy_drift:
        policy_versions = await list_managed_policy_versions(iam_client, policy_arn)
        if len(policy_versions) == 5:
            await boto_crud_call(
                iam_client.delete_policy_version,
                PolicyArn=policy_arn,
                VersionId=get_oldest_policy_version_id(policy_versions),
            )

    log_str = f"{log_str} Updating PolicyDocument..."
    await boto_crud_call(
        iam_client.create_policy_version,
        PolicyArn=policy_arn,
        PolicyDocument=json.dumps(template_policy_document),
    )
    log.debug(log_str, **log_params)


async def apply_managed_policy_tags(
    iam_client,
    policy_arn: str,
    template_tags: list[dict],
    existing_tags: list[dict],
    log_params: dict,
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
                resource_type="aws:policy_document",
                resource_id=policy_arn,
                change_summary={"TagKeys": tags_to_remove},
            )
        ]
        response.extend(proposed_changes)

        if ctx.execute:
            log_str = f"{log_str} Removing tags..."
            apply_awaitable = boto_crud_call(
                iam_client.untag_policy,
                PolicyArn=policy_arn,
                TagKeys=tags_to_remove,
            )
            tasks.append(plugin_apply_wrapper(apply_awaitable, proposed_changes))
        log.debug(log_str, tags=tags_to_remove, **log_params)

    if tags_to_apply:
        log_str = "New tags discovered in AWS."
        proposed_changes = [
            ProposedChange(
                change_type=ProposedChangeType.ATTACH,
                resource_type="aws:policy_document",
                resource_id=policy_arn,
                attribute="tags",
                new_value=tag,
            )
            for tag in tags_to_apply
        ]
        response.extend(proposed_changes)
        if ctx.execute:
            log_str = f"{log_str} Adding tags..."
            apply_awaitable = boto_crud_call(
                iam_client.tag_policy, PolicyArn=policy_arn, Tags=tags_to_apply
            )
            tasks.append(plugin_apply_wrapper(apply_awaitable, proposed_changes))
        log.debug(log_str, tags=tags_to_apply, **log_params)

    if tasks:
        results: list[list[ProposedChange]] = await asyncio.gather(*tasks)
        return list(chain.from_iterable(results))
    else:
        return response


async def get_managed_policy_across_accounts(
    aws_accounts: list[AWSAccount], managed_policy_path: str, managed_policy_name: str
) -> dict:
    async def get_managed_policy_for_account(aws_account: AWSAccount):
        iam_client = await aws_account.get_boto3_client("iam")
        arn = f"arn:aws:iam::{aws_account.account_id}:policy{managed_policy_path}{managed_policy_name}"
        return {aws_account.account_id: await get_managed_policy(iam_client, arn)}

    account_on_managed_policies = await asyncio.gather(
        *[get_managed_policy_for_account(aws_account) for aws_account in aws_accounts]
    )
    return {
        account_id: mp
        for resp in account_on_managed_policies
        for account_id, mp in resp.items()
    }
