from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta
from typing import Any, Optional, Union

from iambic.core.logger import log
from iambic.plugins.v0_1_0.aws.models import (
    IAMBIC_HUB_ROLE_NAME,
    IAMBIC_SPOKE_ROLE_NAME,
    get_hub_role_arn,
)
from iambic.plugins.v0_1_0.aws.utils import boto_crud_call, legacy_paginated_search

TEMPLATE_DIR = f"{str(os.path.dirname(__file__))}/templates"


def get_rule_forwarding_template_body() -> str:
    template = f"{TEMPLATE_DIR}/IdentityRuleForwarder.yml"
    with open(template, "r") as f:
        return f.read()


def get_central_rule_template_body() -> str:
    template = f"{TEMPLATE_DIR}/IdentityRuleDestination.yml"
    with open(template, "r") as f:
        return f.read()


def get_iambic_hub_role_template_body() -> str:
    template = f"{TEMPLATE_DIR}/IambicHubRole.yml"
    with open(template, "r") as f:
        return f.read()


def get_iambic_spoke_role_template_body(read_only=False) -> str:
    suffix = "ReadOnly" if read_only else ""
    template = f"{TEMPLATE_DIR}/IambicSpokeRole{suffix}.yml"
    with open(template, "r") as f:
        return f.read()


async def delete_stack(client, stack_name: str, **kwargs):
    try:
        existing_stack = await legacy_paginated_search(
            client.describe_stacks,
            response_key="Stacks",
            StackName=stack_name,
        )
        if not existing_stack:
            log.info(
                "Stack does not exist. Skipping deletion.",
                stack_name=stack_name,
            )
            return True
    except client.exceptions.ClientError as e:
        # ValidationError means the stack doesn't exist
        if e.response["Error"]["Code"] != "ValidationError":
            raise

    response = await boto_crud_call(
        client.delete_stack,
        StackName=stack_name,
        **kwargs,
    )

    resource_status = "DELETE_IN_PROGRESS"

    estimated_completion = (datetime.now() + timedelta(minutes=3)).strftime(
        "%m/%d/%Y, %H:%M:%S"
    )

    while resource_status == "DELETE_IN_PROGRESS":
        log.info(
            "Waiting for stack to be deleted.",
            stack_name=stack_name,
            estimated_completion=estimated_completion,
        )
        await asyncio.sleep(30)
        try:
            response = await legacy_paginated_search(
                client.describe_stacks,
                response_key="Stacks",
                StackName=stack_name,
            )
        except client.exceptions.ClientError as e:
            # ValidationError means the stack doesn't exist
            if e.response["Error"]["Code"] != "ValidationError":
                raise
            response = []
        if not response:
            return True

        stack_details = response[0]
        resource_status = stack_details.get("StackStatus")

    log.error(
        "Unable to delete AWS CloudFormation Stack",
        stack_name=stack_name,
        reason=stack_details.get("StackStatusReason"),
    )
    return False


async def create_stack(
    client, stack_name: str, template_body: str, parameters: list[dict], **kwargs
) -> bool:
    region = client.meta.region_name

    try:
        existing_stack = await legacy_paginated_search(
            client.describe_stacks,
            response_key="Stacks",
            StackName=stack_name,
        )
        if existing_stack:
            log.info(
                "Stack already exists. Skipping creation. "
                "If this is not the desired behavior, please delete the stack in the console and try again.\n",
                stack_name=stack_name,
                stack_url=f"https://{region}.console.aws.amazon.com/cloudformation/home?region={region}#/stacks\n",
            )
            return True
    except client.exceptions.ClientError as e:
        # ValidationError means the stack doesn't exist
        if e.response["Error"]["Code"] != "ValidationError":
            raise

    response: dict = await boto_crud_call(
        client.create_stack,
        StackName=stack_name,
        TemplateBody=template_body,
        Parameters=parameters,
        OnFailure="ROLLBACK",
        **kwargs,
    )

    stack_id = response.get("StackId")
    resource_status = "CREATE_IN_PROGRESS"

    estimated_completion = (datetime.now() + timedelta(minutes=3)).strftime(
        "%m/%d/%Y, %H:%M:%S"
    )

    while resource_status == "CREATE_IN_PROGRESS":
        log.info(
            "Waiting for stack to be created.",
            stack_name=stack_name,
            estimated_completion=estimated_completion,
        )
        await asyncio.sleep(30)
        response = await legacy_paginated_search(
            client.describe_stacks,
            response_key="Stacks",
            StackName=stack_name,
        )
        stack_details = [stack for stack in response if stack["StackId"] == stack_id]
        if stack_details:
            stack_details = stack_details[0]
        else:
            stack_details = {
                "StackStatus": "CREATE_FAILED",
                "StackStatusReason": f"Stack not found. Stack Name: {stack_name}, Stack ID: {stack_id}",
            }
        resource_status = stack_details.get("StackStatus")

    if resource_status == "CREATE_FAILED":
        soft_fail = bool("already exists." in stack_details.get("StackStatusReason"))
        if soft_fail:
            log.warning(
                "Role already exists on account.",
                stack_name=stack_name,
                reason=stack_details.get("StackStatusReason"),
            )
        else:
            log.error(
                "Unable to create AWS CloudFormation Stack",
                stack_name=stack_name,
                reason=stack_details.get("StackStatusReason"),
            )
        return soft_fail
    return True


async def delete_stack_set(client, stack_set_name):
    try:
        client.delete_stack_set(StackSetName=stack_set_name)
    except client.exceptions.StackSetNotFoundException:
        log.warning(
            f"Stack set {stack_set_name} not found. Deletion skipped.",
            stack_set_name=stack_set_name,
        )
        return

    except client.exceptions.OperationInProgressException:
        log.info(
            "Stack set deletion already in progress",
            stack_set_name=stack_set_name,
        )
        pass

    while True:
        try:
            response = client.describe_stack_set_operation(
                StackSetName=stack_set_name,
                OperationId="DELETE",
            )
            operation_status = response.get("StackSetOperation", {}).get("Status")
            if operation_status == "RUNNING":
                log.info(
                    "Waiting for stack set deletion to complete",
                    stack_set_name=stack_set_name,
                )
                await asyncio.sleep(30)
            elif operation_status == "SUCCEEDED":
                log.info(
                    "Stack set deletion completed successfully",
                    stack_set_name=stack_set_name,
                )
                return
            else:
                log.error(
                    "Stack set deletion failed",
                    stack_set_name=stack_set_name,
                    operation_status=operation_status,
                )
                return
        except (
            client.exceptions.StackSetNotFoundException,
            client.exceptions.OperationNotFoundException,
        ):
            log.info(
                "Stack set deleted successfully",
                stack_set_name=stack_set_name,
            )
            return


async def create_stack_set(
    client,
    stack_set_name,
    template_body: str,
    parameters: list[dict],
    deployment_targets: dict,
    deployment_regions: list[str],
    operation_preferences: dict[str, Union[int, str]],
    **kwargs,
) -> bool:
    region = client.meta.region_name

    try:
        await boto_crud_call(
            client.describe_stack_set,
            StackSetName=stack_set_name,
        )
        log.info(
            "StackSet already exists. Skipping creation. "
            "If this is not the desired behavior, please delete the stack in the console and try again.\n",
            stack_set_name=stack_set_name,
            stack_set_url=f"https://{region}.console.aws.amazon.com/cloudformation/home?region={region}#/stacksets\n",
        )
        return True
    except client.exceptions.StackSetNotFoundException:
        pass

    await boto_crud_call(
        client.create_stack_set,
        StackSetName=stack_set_name,
        TemplateBody=template_body,
        Parameters=parameters,
        PermissionModel="SERVICE_MANAGED",
        AutoDeployment={"Enabled": True, "RetainStacksOnAccountRemoval": True},
        ManagedExecution={"Active": True},
        **kwargs,
    )

    await boto_crud_call(
        client.create_stack_instances,
        StackSetName=stack_set_name,
        DeploymentTargets=deployment_targets,
        Regions=deployment_regions,
        OperationPreferences=operation_preferences,
    )

    await asyncio.sleep(30)  # Wait for stack instances to be created

    while True:
        stack_instances = await legacy_paginated_search(
            client.list_stack_instances,
            response_key="Summaries",
            StackSetName=stack_set_name,
        )
        pending_count = len(
            [
                instance
                for instance in stack_instances
                if instance.get("StackInstanceStatus", {}).get("DetailedStatus")
                in ["PENDING", "RUNNING"]
            ]
        )
        if pending_count:
            log.info(
                "Waiting for stack set instances to be created",
                stack_set_name=stack_set_name,
                pending_instances=pending_count,
                estimated_completion=(
                    datetime.now() + timedelta(minutes=pending_count * 1.5)
                ).strftime("%m/%d/%Y, %H:%M:%S"),
            )
            await asyncio.sleep(30)
            continue
        elif all(
            instance.get("StackInstanceStatus", {}).get("DetailedStatus") == "SUCCEEDED"
            for instance in stack_instances
        ):
            return True
        else:
            existing_instances = []
            failed_instances = []
            for instance in stack_instances:
                if instance.get("StackInstanceStatus", {}).get("DetailedStatus") in [
                    "FAILED",
                    "CANCELLED",
                ]:
                    response_summary = {
                        "Account": instance["Account"],
                        "Region": instance["Region"],
                        "Status": instance.get("StackInstanceStatus", {}).get(
                            "DetailedStatus"
                        ),
                        "StatusReason": instance.get("StatusReason"),
                    }
                    if "already exists." in instance.get("StatusReason"):
                        existing_instances.append(response_summary)
                    else:
                        failed_instances.append(response_summary)

            if existing_instances:
                log.warning(
                    "Role already exists on account(s).",
                    stack_set_name=stack_set_name,
                    failed_instances=failed_instances,
                )
            if failed_instances:
                log.error(
                    "Unable to create stack set instances",
                    stack_set_name=stack_set_name,
                    failed_instances=failed_instances,
                )

            return not bool(failed_instances)


async def delete_change_detection_stacks(cf_client):
    # The delete_stack function is assumed to exist in your code. You might need to adjust its parameters.
    stack_deleted = await delete_stack(
        cf_client,
        stack_name="IAMbicForwardEventRule",
    )
    if stack_deleted:
        stack_deleted = await delete_stack(
            cf_client,
            stack_name="IAMbicCentralChangeRule",
        )

    return stack_deleted


async def create_change_detection_stacks(
    cf_client,
    org_id: str,
    org_account_id: str,
    role_arn: Optional[str] = None,
    tags: Optional[dict] = None,
) -> bool:
    region = cf_client.meta.region_name
    additional_kwargs: dict[str, Any] = {"RoleARN": role_arn} if role_arn else {}

    if tags:
        additional_kwargs["Tags"] = tags

    stack_created = await create_stack(
        cf_client,
        stack_name="IAMbicCentralChangeRule",
        template_body=get_central_rule_template_body(),
        parameters=[{"ParameterKey": "OrgID", "ParameterValue": org_id}],
        **additional_kwargs,
    )
    if stack_created:
        stack_created = await create_stack(
            cf_client,
            stack_name="IAMbicForwardEventRule",
            template_body=get_rule_forwarding_template_body(),
            parameters=[
                {
                    "ParameterKey": "TargetEventBusArn",
                    "ParameterValue": f"arn:aws:events:{region}:{org_account_id}:event-bus/IAMbicChangeDetectionEventBus",
                }
            ],
            Capabilities=["CAPABILITY_NAMED_IAM"],
            **additional_kwargs,
        )

    return stack_created


async def delete_change_detection_stack_sets(
    cf_client,
    org_client,
):
    stack_set_name = "IAMbicForwardEventRule"

    await delete_stack_instances(cf_client, org_client, stack_set_name)

    # Delete stack set
    await delete_stack_set(cf_client, stack_set_name)

    return True


async def create_change_detection_stack_sets(
    cf_client, org_client, org_account_id: str, tags: Optional[dict] = None
) -> bool:
    region = cf_client.meta.region_name
    org_roots = await legacy_paginated_search(
        org_client.list_roots, response_key="Roots"
    )
    kwargs = {}
    if tags:
        kwargs["Tags"] = tags

    return await create_stack_set(
        cf_client,
        stack_set_name="IAMbicForwardEventRule",
        template_body=get_rule_forwarding_template_body(),
        parameters=[
            {
                "ParameterKey": "TargetEventBusArn",
                "ParameterValue": f"arn:aws:events:{region}:{org_account_id}:event-bus/IAMbicChangeDetectionEventBus",
            }
        ],
        deployment_targets={
            "OrganizationalUnitIds": [root["Id"] for root in org_roots],
            "AccountFilterType": "NONE",
        },
        deployment_regions=[region],
        operation_preferences={
            "MaxConcurrentCount": 1,
            "FailureToleranceCount": 1,
        },
        Capabilities=["CAPABILITY_NAMED_IAM"],
        **kwargs,
    )


async def delete_iambic_eventbridge_stacks(
    cf_client,
    org_client,
    org_id: str,
    account_id: str,
    role_arn: Optional[str] = None,
    tags=None,
) -> bool:

    region = cf_client.meta.region_name
    successfully_deleted = await delete_change_detection_stacks(
        cf_client,
    )
    if successfully_deleted:
        log.info(
            f"WARNING: Do not exit; creating stack instances.\n"
            f"You can check the progress here:\n"
            f"https://{region}.console.aws.amazon.com/cloudformation/home?region={region}#/stacksets/IAMbicForwardEventRule/stacks\n"
        )
        return await delete_change_detection_stack_sets(
            cf_client,
            org_client,
        )

    return successfully_deleted


async def create_iambic_eventbridge_stacks(
    cf_client,
    org_client,
    org_id: str,
    account_id: str,
    role_arn: Optional[str] = None,
    tags=None,
) -> bool:

    region = cf_client.meta.region_name
    successfully_created = await create_change_detection_stacks(
        cf_client, org_id, account_id, role_arn, tags
    )
    if successfully_created:
        log.info(
            f"WARNING: Do not exit; creating stack instances.\n"
            f"You can check the progress here:\n"
            f"https://{region}.console.aws.amazon.com/cloudformation/home?region={region}#/stacksets/IAMbicForwardEventRule/stacks\n"
        )
        return await create_change_detection_stack_sets(
            cf_client, org_client, account_id, tags
        )

    return successfully_created


async def delete_stack_instances(
    cf_client,
    org_client,
    stack_set_name,
):
    org_roots = await legacy_paginated_search(
        org_client.list_roots, response_key="Roots"
    )
    while True:
        try:
            response = cf_client.list_stack_instances(StackSetName=stack_set_name)

            stack_instances = [
                instance
                for instance in response["Summaries"]
                if instance["Status"]
                in ["CURRENT", "CREATE_COMPLETE", "UPDATE_COMPLETE"]
            ]
        except cf_client.exceptions.StackSetNotFoundException:
            stack_instances = None

        if not stack_instances:
            log.info(
                "No stack instances found. Deletion of stack instances complete.",
                stack_set_name=stack_set_name,
            )
            return

        accounts = set()
        regions = set()
        for instance in stack_instances:
            account = instance.get("Account")
            region = instance.get("Region")
            accounts.add(account)
            regions.add(region)

        cf_client.delete_stack_instances(
            StackSetName=stack_set_name,
            Regions=list(regions),
            RetainStacks=False,
            DeploymentTargets={
                "OrganizationalUnitIds": [root["Id"] for root in org_roots],
                "AccountFilterType": "NONE",
            },
        )

        log.info(
            "Waiting for stack instances to be deleted",
            stack_set_name=stack_set_name,
        )
        await asyncio.sleep(30)


async def delete_spoke_role_stack_set(
    cf_client,
    org_client,
    stack_set_name=IAMBIC_SPOKE_ROLE_NAME,
):
    # Delete stack instances
    await delete_stack_instances(
        cf_client,
        org_client,
        stack_set_name,
    )

    # Delete stack set
    await delete_stack_set(cf_client, stack_set_name)


async def create_spoke_role_stack_set(
    cf_client,
    org_client,
    hub_account_id: str,
    read_only=False,
    stack_set_name=IAMBIC_SPOKE_ROLE_NAME,
    hub_role_name=IAMBIC_HUB_ROLE_NAME,
    spoke_role_name=IAMBIC_SPOKE_ROLE_NAME,
    tags=None,
) -> bool:
    """Create stack instances in the member accounts.
    This does not have special handling for delegated
    administrator membership account.
    TODO: If the org has delegated administrator account,
    the IambicHubRole should be installed on delegated
    administrator account.
    """
    region = cf_client.meta.region_name
    org_roots = await legacy_paginated_search(
        org_client.list_roots, response_key="Roots"
    )

    kwargs = {}

    if tags:
        kwargs["Tags"] = tags

    return await create_stack_set(
        cf_client,
        stack_set_name=stack_set_name,
        template_body=get_iambic_spoke_role_template_body(read_only=read_only),
        parameters=[
            {
                "ParameterKey": "HubRoleArn",
                "ParameterValue": get_hub_role_arn(
                    hub_account_id, role_name=hub_role_name
                ),
            },
            {"ParameterKey": "SpokeRoleName", "ParameterValue": spoke_role_name},
        ],
        deployment_targets={
            "OrganizationalUnitIds": [root["Id"] for root in org_roots],
            "AccountFilterType": "NONE",
        },
        deployment_regions=[region],
        operation_preferences={
            "RegionConcurrencyType": "PARALLEL",
            "MaxConcurrentCount": 10,
            "FailureToleranceCount": 10,
        },
        Capabilities=["CAPABILITY_NAMED_IAM"],
        **kwargs,
    )


async def create_spoke_role_stack(
    cf_client,
    hub_account_id: str,
    role_arn: Optional[str] = None,
    read_only=False,
    stack_name=IAMBIC_SPOKE_ROLE_NAME,
    hub_role_name=IAMBIC_HUB_ROLE_NAME,
    spoke_role_name=IAMBIC_SPOKE_ROLE_NAME,
    tags=None,
) -> bool:
    additional_kwargs = {"RoleARN": role_arn} if role_arn else {}
    if tags:
        additional_kwargs["Tags"] = tags
    return await create_stack(
        cf_client,
        stack_name=stack_name,
        template_body=get_iambic_spoke_role_template_body(read_only=read_only),
        parameters=[
            {
                "ParameterKey": "HubRoleArn",
                "ParameterValue": get_hub_role_arn(
                    hub_account_id, role_name=hub_role_name
                ),
            },
            {
                "ParameterKey": "SpokeRoleName",
                "ParameterValue": spoke_role_name,
            },
        ],
        Capabilities=["CAPABILITY_NAMED_IAM"],
        **additional_kwargs,
    )


async def delete_hub_account_stacks(cf_client, stack_name):
    try:
        await cf_client.delete_stack(StackName=stack_name)
        log.info("Deleting stack in the hub account", stack_name=stack_name)
    except cf_client.exceptions.StackDoesNotExist:
        log.warning("Stack does not exist in the hub account", stack_name=stack_name)
    except cf_client.exceptions.ClientError as e:
        log.error(
            "Failed to delete stack in the hub account",
            stack_name=stack_name,
            error=str(e),
        )
        return False

    return True


async def create_hub_account_stacks(
    cf_client,
    hub_account_id: str,
    assume_as_arn: str,
    role_arn: Optional[str] = None,
    read_only=False,
    stack_name=IAMBIC_HUB_ROLE_NAME,
    hub_role_name=IAMBIC_HUB_ROLE_NAME,
    spoke_role_name=IAMBIC_SPOKE_ROLE_NAME,
    tags=None,
) -> bool:
    """Create IambicHubRole and IambicSpokeRole in hub account"""
    additional_kwargs = {"RoleARN": role_arn} if role_arn else {}
    if tags:
        additional_kwargs["Tags"] = tags

    stack_created = await create_stack(
        cf_client,
        stack_name=stack_name,
        template_body=get_iambic_hub_role_template_body(),
        parameters=[
            {"ParameterKey": "HubRoleName", "ParameterValue": hub_role_name},
            {
                "ParameterKey": "SpokeRoleName",
                "ParameterValue": spoke_role_name,
            },
            {"ParameterKey": "AssumeAsArn", "ParameterValue": assume_as_arn},
        ],
        Capabilities=["CAPABILITY_NAMED_IAM"],
        **additional_kwargs,
    )
    if stack_created:
        return await create_spoke_role_stack(
            cf_client,
            hub_account_id,
            role_arn,
            read_only=read_only,
            stack_name=spoke_role_name,
            hub_role_name=hub_role_name,
            spoke_role_name=spoke_role_name,
            tags=tags,
        )

    return stack_created


async def delete_iambic_role_stacks(
    cf_client,
    org_client=None,
    hub_role_stack_name=IAMBIC_HUB_ROLE_NAME,
    spoke_role_stack_name=IAMBIC_SPOKE_ROLE_NAME,
):
    # Delete spoke role stack set
    await delete_spoke_role_stack_set(
        cf_client,
        org_client,
        spoke_role_stack_name,
    )

    # Delete hub account stacks
    await delete_hub_account_stacks(
        cf_client,
        hub_role_stack_name,
    )


async def create_iambic_role_stacks(
    cf_client,
    hub_account_id: str,
    assume_as_arn: str,
    role_arn: Optional[str] = None,
    org_client=None,
    read_only=False,
    hub_role_stack_name=IAMBIC_HUB_ROLE_NAME,
    hub_role_name=IAMBIC_HUB_ROLE_NAME,
    spoke_role_stack_name=IAMBIC_SPOKE_ROLE_NAME,
    spoke_role_name=IAMBIC_SPOKE_ROLE_NAME,
    tags=None,
) -> bool:
    hub_role_created = await create_hub_account_stacks(
        cf_client,
        hub_account_id,
        assume_as_arn,
        role_arn,
        read_only=read_only,
        stack_name=hub_role_stack_name,
        hub_role_name=hub_role_name,
        spoke_role_name=spoke_role_name,
        tags=tags,
    )
    region = cf_client.meta.region_name
    if hub_role_created and org_client:
        log.info(
            f"WARNING: Do not exit; creating stack instances.\n"
            f"You can check the progress here:\n"
            f"https://{region}.console.aws.amazon.com/cloudformation/home?region={region}#/stacksets/{spoke_role_name}/stacks\n"
        )
        return await create_spoke_role_stack_set(
            cf_client,
            org_client,
            hub_account_id,
            read_only=read_only,
            stack_set_name=spoke_role_stack_name,
            hub_role_name=hub_role_name,
            spoke_role_name=spoke_role_name,
            tags=tags,
        )

    return hub_role_created
