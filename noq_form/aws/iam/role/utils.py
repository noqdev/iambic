import asyncio
import json

from deepdiff import DeepDiff

from noq_form.core.context import ctx
from noq_form.core.logger import log
from noq_form.core.utils import aio_wrapper


async def get_role_inline_policy_names(role_name: str, iam_client):
    marker: dict[str, str] = {}
    inline_policies = []

    while True:
        response = await aio_wrapper(
            iam_client.list_role_policies, RoleName=role_name, **marker
        )
        inline_policies.extend(response["PolicyNames"])

        if response["IsTruncated"]:
            marker["Marker"] = response["Marker"]
        else:
            return inline_policies


async def get_role_instance_profiles(role_name: str, iam_client):
    marker: dict[str, str] = {}
    instance_profiles = []

    while True:
        response = await aio_wrapper(
            iam_client.list_instance_profiles_for_role, RoleName=role_name, **marker
        )
        instance_profiles.extend(response["InstanceProfiles"])

        if response["IsTruncated"]:
            marker["Marker"] = response["Marker"]
        else:
            return instance_profiles


async def get_role_policy(role_name: str, policy_name: str, iam_client):
    return await aio_wrapper(
        iam_client.get_role_policy, RoleName=role_name, PolicyName=policy_name
    )


async def get_role_inline_policies(role_name: str, iam_client):
    policy_names = await get_role_inline_policy_names(role_name, iam_client)
    policies = await asyncio.gather(
        *[
            get_role_policy(role_name, policy_name, iam_client)
            for policy_name in policy_names
        ]
    )
    return {policy["PolicyName"]: policy["PolicyDocument"] for policy in policies}


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


async def apply_role_tags(
    role_name: str,
    iam_client,
    template_tags: list[dict],
    existing_tags: list[dict],
    log_params: dict,
) -> bool:
    existing_tag_map = {tag["Key"]: tag["Value"] for tag in existing_tags}
    template_tag_map = {tag["Key"]: tag["Value"] for tag in template_tags}
    tags_to_apply = [
        tag for tag in template_tags if tag["Value"] != existing_tag_map.get(tag["Key"])
    ]
    tasks = []
    changes_made = False

    if tags_to_remove := [
        tag["Key"] for tag in existing_tags if not template_tag_map.get(tag["Key"])
    ]:
        changes_made = True
        log_str = "Stale tags discovered."
        if ctx.execute:
            log_str = f"{log_str} Removing tags..."
            log.info(log_str, tags=tags_to_remove, **log_params)
            tasks.append(
                aio_wrapper(
                    iam_client.untag_role, RoleName=role_name, TagKeys=tags_to_remove
                )
            )
        else:
            log.info(log_str, tags=tags_to_remove, **log_params)

    if tags_to_apply:
        changes_made = True
        log_str = "New tags discovered in AWS."
        if ctx.execute:
            log_str = f"{log_str} Adding tags..."
            log.info(log_str, tags=tags_to_apply, **log_params)
            tasks.append(
                aio_wrapper(iam_client.tag_role, RoleName=role_name, Tags=tags_to_apply)
            )
        else:
            log.info(log_str, tags=tags_to_apply, **log_params)

    if tasks:
        await asyncio.gather(*tasks)

    return changes_made


async def update_assume_role_policy(
    role_name,
    iam_client,
    template_policy_document: dict,
    existing_policy_document: str,
    log_params: dict,
) -> bool:
    if existing_policy_document and isinstance(existing_policy_document, str):
        existing_policy_document = json.loads(existing_policy_document)

    if not existing_policy_document or bool(
        await aio_wrapper(
            DeepDiff,
            template_policy_document,
            existing_policy_document,
            ignore_order=True,
        )
    ):

        log_str = "Changes to the AssumeRolePolicyDocument discovered."
        if ctx.execute:
            boto_action = "Creating" if existing_policy_document else "Updating"
            log_str = f"{log_str} {boto_action} AssumeRolePolicyDocument..."
            log.info(log_str, **log_params)
            await aio_wrapper(
                iam_client.update_assume_role_policy,
                RoleName=role_name,
                PolicyDocument=json.dumps(template_policy_document),
            )
        else:
            log.info(log_str, **log_params)

        return True

    return False


async def apply_role_managed_policies(
    role_name,
    iam_client,
    template_policies: list[dict],
    role_exists: bool,
    log_params: dict,
) -> bool:
    changes_made = False
    tasks = []
    template_policies = [policy["PolicyArn"] for policy in template_policies]
    if role_exists:
        managed_policies_resp = await get_role_managed_policies(role_name, iam_client)
        existing_managed_policies = [
            policy["PolicyArn"] for policy in managed_policies_resp
        ]
    else:
        existing_managed_policies = []

    new_managed_policies = [
        policy_arn
        for policy_arn in template_policies
        if policy_arn not in existing_managed_policies
    ]
    if new_managed_policies:
        changes_made = False
        log_str = "New managed policies discovered."
        if ctx.execute:
            log_str = f"{log_str} Adding managed policies..."
            log.info(log_str, managed_policies=new_managed_policies, **log_params)
            tasks = [
                aio_wrapper(
                    iam_client.attach_role_policy,
                    RoleName=role_name,
                    PolicyArn=policy_arn,
                )
                for policy_arn in new_managed_policies
            ]
        else:
            log.info(log_str, managed_policies=new_managed_policies, **log_params)

    existing_managed_policies = [
        policy_arn
        for policy_arn in existing_managed_policies
        if policy_arn not in template_policies
    ]
    if existing_managed_policies:
        log_str = "Stale managed policies discovered."
        if ctx.execute:
            log_str = f"{log_str} Removing managed policies..."
            log.info(log_str, managed_policies=existing_managed_policies, **log_params)
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
        else:
            log.info(log_str, managed_policies=existing_managed_policies, **log_params)

    if tasks:
        await asyncio.gather(*tasks)

    return changes_made


async def apply_role_inline_policies(
    role_name,
    iam_client,
    template_policies: list[dict],
    role_exists: bool,
    log_params: dict,
) -> bool:
    tasks = []
    changes_made = False

    if role_exists:
        template_policy_map = {
            policy["PolicyName"]: policy["PolicyDocument"]
            for policy in template_policies
        }
        existing_policy_map = await get_role_inline_policies(role_name, iam_client)

        for policy_name in existing_policy_map.keys():
            if not template_policy_map.get(policy_name):
                changes_made = True
                log_str = "Stale inline policies discovered."
                if ctx.execute:
                    log_str = f"{log_str} Removing inline policy..."
                    log.info(log_str, policy_name=policy_name, **log_params)
                    tasks.append(
                        aio_wrapper(
                            iam_client.delete_role_policy,
                            RoleName=role_name,
                            PolicyName=policy_name,
                        )
                    )
                else:
                    log.info(log_str, policy_name=policy_name, **log_params)

        for policy_name, policy_document in template_policy_map.items():
            existing_policy_doc = existing_policy_map.get(policy_name)
            if not existing_policy_doc or (
                await aio_wrapper(
                    DeepDiff, policy_document, existing_policy_doc, ignore_order=True
                )
            ):
                changes_made = True
                resource_existence = "New" if not existing_policy_doc else "Stale"
                log_str = f"{resource_existence} inline policies discovered."
                if ctx.execute:
                    boto_action = "Creating" if not existing_policy_doc else "Updating"
                    log_str = f"{log_str} {boto_action} inline policy..."
                    log.info(log_str, policy_name=policy_name, **log_params)

                    tasks.append(
                        aio_wrapper(
                            iam_client.put_role_policy,
                            RoleName=role_name,
                            PolicyName=policy_name,
                            PolicyDocument=json.dumps(policy_document),
                        )
                    )
                else:
                    log.info(log_str, policy_name=policy_name, **log_params)

        if tasks:
            await asyncio.gather(*tasks)

    return changes_made


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
