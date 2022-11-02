import asyncio
import json
from typing import Union

from deepdiff import DeepDiff

from iambic.aws.utils import paginated_search
from iambic.core.context import ctx
from iambic.core.logger import log
from iambic.core.models import ProposedChange, ProposedChangeType
from iambic.core.utils import aio_wrapper


async def get_role_inline_policy_names(role_name: str, iam_client):
    return await paginated_search(
        iam_client.list_role_policies, "PolicyNames", RoleName=role_name
    )


async def get_role_instance_profiles(role_name: str, iam_client):
    return await paginated_search(
        iam_client.list_instance_profiles_for_role,
        "InstanceProfiles",
        RoleName=role_name,
    )


async def list_roles(iam_client):
    return await paginated_search(iam_client.list_roles, "Roles")


async def list_role_tags(role_name: str, iam_client):
    return await paginated_search(iam_client.list_role_tags, "Tags", RoleName=role_name)


async def get_role_policy(role_name: str, policy_name: str, iam_client):
    return await aio_wrapper(
        iam_client.get_role_policy, RoleName=role_name, PolicyName=policy_name
    )


async def get_role_inline_policies(
    role_name: str, iam_client, as_dict: bool = True
) -> Union[list , dict]:
    policy_names = await get_role_inline_policy_names(role_name, iam_client)
    policies = await asyncio.gather(
        *[
            get_role_policy(role_name, policy_name, iam_client)
            for policy_name in policy_names
        ]
    )
    if as_dict:
        return {policy["PolicyName"]: policy["PolicyDocument"] for policy in policies}
    else:
        return [
            {"PolicyName": policy["PolicyName"], **policy["PolicyDocument"]}
            for policy in policies
        ]


async def get_role_managed_policies(role_name: str, iam_client) -> list[dict[str, str]]:
    marker: dict[str, str] = {}
    policies = []

    while True:
        response = await aio_wrapper(
            iam_client.list_attached_role_policies, RoleName=role_name, **marker
        )
        policies.extend(response["AttachedPolicies"])

        if response["IsTruncated"]:
            marker["Marker"] = response["Marker"]
        else:
            break

    return policies


async def get_role(role_name: str, iam_client):
    try:
        current_role = (await aio_wrapper(iam_client.get_role, RoleName=role_name))[
            "Role"
        ]
        current_role["ManagedPolicies"] = await get_role_managed_policies(
            role_name, iam_client
        )
        current_role["InlinePolicies"] = await get_role_inline_policies(
            role_name, iam_client, as_dict=False
        )
    except iam_client.exceptions.NoSuchEntityException:
        current_role = {}

    return current_role


async def apply_role_tags(
    role_name: str,
    iam_client,
    template_tags: list[dict],
    existing_tags: list[dict],
    log_params: dict,
) -> list[ProposedChange]:
    existing_tag_map = {tag["Key"]: tag["Value"] for tag in existing_tags}
    template_tag_map = {tag["Key"]: tag["Value"] for tag in template_tags}
    tags_to_apply = [
        tag for tag in template_tags if tag["Value"] != existing_tag_map.get(tag["Key"])
    ]
    tasks = []
    response = []

    if tags_to_remove := [
        tag["Key"] for tag in existing_tags if not template_tag_map.get(tag["Key"])
    ]:
        log_str = "Stale tags discovered."
        response.append(
            ProposedChange(
                change_type=ProposedChangeType.DETACH,
                attribute="tags",
                change_summary={"TagKeys": tags_to_remove},
            )
        )
        if ctx.execute:
            log_str = f"{log_str} Removing tags..."
            tasks.append(
                aio_wrapper(
                    iam_client.untag_role, RoleName=role_name, TagKeys=tags_to_remove
                )
            )
        log.info(log_str, tags=tags_to_remove, **log_params)

    if tags_to_apply:
        log_str = "New tags discovered in AWS."
        for tag in tags_to_apply:
            response.append(
                ProposedChange(
                    change_type=ProposedChangeType.ATTACH,
                    attribute="tags",
                    new_value=tag,
                )
            )
        if ctx.execute:
            log_str = f"{log_str} Adding tags..."
            tasks.append(
                aio_wrapper(iam_client.tag_role, RoleName=role_name, Tags=tags_to_apply)
            )
        log.info(log_str, tags=tags_to_apply, **log_params)

    if tasks:
        await asyncio.gather(*tasks)

    return response


async def update_assume_role_policy(
    role_name,
    iam_client,
    template_policy_document: dict,
    existing_policy_document: str,
    log_params: dict,
) -> list[ProposedChange]:
    response = []
    policy_drift = None

    if existing_policy_document:
        if isinstance(existing_policy_document, str):
            existing_policy_document = json.loads(existing_policy_document)

        policy_drift = await aio_wrapper(
            DeepDiff,
            existing_policy_document,
            template_policy_document,
            ignore_order=True,
        )

    if not existing_policy_document or bool(policy_drift):
        log_str = "Changes to the AssumeRolePolicyDocument discovered."
        if policy_drift:
            response.append(
                ProposedChange(
                    change_type=ProposedChangeType.UPDATE,
                    attribute="assume_role_policy_document",
                    change_summary=policy_drift,
                    current_value=existing_policy_document,
                    new_value=template_policy_document,
                )
            )
        else:
            response.append(
                ProposedChange(
                    change_type=ProposedChangeType.CREATE,
                    attribute="assume_role_policy_document",
                    new_value=template_policy_document,
                )
            )

        if ctx.execute:
            boto_action = "Creating" if existing_policy_document else "Updating"
            log_str = f"{log_str} {boto_action} AssumeRolePolicyDocument..."
            await aio_wrapper(
                iam_client.update_assume_role_policy,
                RoleName=role_name,
                PolicyDocument=json.dumps(template_policy_document),
            )
        log.info(log_str, **log_params)

    return response


async def apply_role_managed_policies(
    role_name,
    iam_client,
    template_policies: list[dict],
    existing_policies: list[dict],
    log_params: dict,
) -> list[ProposedChange]:
    tasks = []
    response = []
    template_policies = [policy["PolicyArn"] for policy in template_policies]
    existing_managed_policies = [policy["PolicyArn"] for policy in existing_policies]

    # Create new managed policies
    new_managed_policies = [
        policy_arn
        for policy_arn in template_policies
        if policy_arn not in existing_managed_policies
    ]
    if new_managed_policies:
        log_str = "New managed policies discovered."
        for policy_arn in new_managed_policies:
            response.append(
                ProposedChange(
                    change_type=ProposedChangeType.ATTACH,
                    resource_id=policy_arn,
                    attribute="managed_policies",
                )
            )
        if ctx.execute:
            log_str = f"{log_str} Adding managed policies..."
            tasks = [
                aio_wrapper(
                    iam_client.attach_role_policy,
                    RoleName=role_name,
                    PolicyArn=policy_arn,
                )
                for policy_arn in new_managed_policies
            ]
        log.info(log_str, managed_policies=new_managed_policies, **log_params)

    # Delete existing managed policies not in template
    existing_managed_policies = [
        policy_arn
        for policy_arn in existing_managed_policies
        if policy_arn not in template_policies
    ]
    if existing_managed_policies:
        log_str = "Stale managed policies discovered."
        for policy_arn in existing_managed_policies:
            response.append(
                ProposedChange(
                    change_type=ProposedChangeType.DETACH,
                    resource_id=policy_arn,
                    attribute="managed_policies",
                )
            )
        if ctx.execute:
            log_str = f"{log_str} Removing managed policies..."
            tasks.extend(
                [
                    aio_wrapper(
                        iam_client.detach_role_policy,
                        RoleName=role_name,
                        PolicyArn=policy_arn,
                    )
                    for policy_arn in existing_managed_policies
                ]
            )
        log.info(log_str, managed_policies=existing_managed_policies, **log_params)

    if tasks:
        await asyncio.gather(*tasks)

    return response


async def apply_role_inline_policies(
    role_name,
    iam_client,
    template_policies: list[dict],
    existing_policies: list[dict],
    log_params: dict,
) -> list[ProposedChange]:
    tasks = []
    response = []
    template_policy_map = {
        policy["PolicyName"]: {k: v for k, v in policy.items() if k != "PolicyName"}
        for policy in template_policies
    }
    existing_policy_map = {
        policy["PolicyName"]: {k: v for k, v in policy.items() if k != "PolicyName"}
        for policy in existing_policies
    }

    for policy_name in existing_policy_map.keys():
        if not template_policy_map.get(policy_name):
            log_str = "Stale inline policies discovered."
            if ctx.execute:
                log_str = f"{log_str} Removing inline policy..."
                response.append(
                    ProposedChange(
                        change_type=ProposedChangeType.DELETE,
                        resource_id=policy_name,
                        attribute="inline_policies",
                    )
                )
                tasks.append(
                    aio_wrapper(
                        iam_client.delete_role_policy,
                        RoleName=role_name,
                        PolicyName=policy_name,
                    )
                )
            log.info(log_str, policy_name=policy_name, **log_params)

    for policy_name, policy_document in template_policy_map.items():
        existing_policy_doc = existing_policy_map.get(policy_name)
        policy_drift = None
        if existing_policy_doc:
            policy_drift = await aio_wrapper(
                DeepDiff,
                existing_policy_doc,
                policy_document,
                ignore_order=True,
            )

        if not existing_policy_doc or policy_drift:
            if policy_drift:
                log_params["policy_drift"] = policy_drift
                boto_action = "Updating"
                resource_existence = "Stale"
                response.append(
                    ProposedChange(
                        change_type=ProposedChangeType.UPDATE,
                        resource_id=policy_name,
                        attribute="inline_policies",
                        change_summary=policy_drift,
                        current_value=existing_policy_doc,
                        new_value=policy_document,
                    )
                )
            else:
                boto_action = "Creating"
                resource_existence = "New"
                response.append(
                    ProposedChange(
                        change_type=ProposedChangeType.CREATE,
                        resource_id=policy_name,
                        attribute="inline_policies",
                        new_value=policy_document,
                    )
                )

            log_str = f"{resource_existence} inline policies discovered."
            if ctx.execute:
                log_str = f"{log_str} {boto_action} inline policy..."
                tasks.append(
                    aio_wrapper(
                        iam_client.put_role_policy,
                        RoleName=role_name,
                        PolicyName=policy_name,
                        PolicyDocument=json.dumps(policy_document),
                    )
                )
            log.info(log_str, policy_name=policy_name, **log_params)

    if tasks:
        await asyncio.gather(*tasks)

    return response


async def delete_iam_role(role_name: str, iam_client, log_params: dict):
    instance_profiles = await get_role_instance_profiles(role_name, iam_client)

    tasks = []
    for instance_profile in instance_profiles:
        tasks.append(
            aio_wrapper(
                iam_client.remove_role_from_instance_profile,
                RoleName=role_name,
                InstanceProfileName=instance_profile["InstanceProfileName"],
            )
        )
    await asyncio.gather(*tasks)

    tasks = []
    for instance_profile in instance_profiles:
        tasks.append(
            aio_wrapper(
                iam_client.delete_instance_profile,
                InstanceProfileName=instance_profile["InstanceProfileName"],
            )
        )
    await asyncio.gather(*tasks)

    tasks = []
    # Detach managed policies
    managed_policies = await get_role_managed_policies(role_name, iam_client)
    managed_policies = [policy["PolicyArn"] for policy in managed_policies]
    log.info(
        "Detaching managed policies.", managed_policies=managed_policies, **log_params
    )
    for policy in managed_policies:
        tasks.append(
            aio_wrapper(
                iam_client.detach_role_policy, RoleName=role_name, PolicyArn=policy
            )
        )

    # Delete inline policies
    inline_policies = await get_role_inline_policies(role_name, iam_client)
    inline_policies = list(inline_policies.keys())
    log.info(
        "Deleting inline policies.", managed_policies=inline_policies, **log_params
    )
    for policy_name in inline_policies:
        tasks.append(
            aio_wrapper(
                iam_client.delete_role_policy,
                RoleName=role_name,
                PolicyName=policy_name,
            )
        )

    # Actually perform the deletion of Managed & Inline policies
    await asyncio.gather(*tasks)
    # Now that everything has been removed from the role, delete the role itself
    await aio_wrapper(iam_client.delete_role, RoleName=role_name)
