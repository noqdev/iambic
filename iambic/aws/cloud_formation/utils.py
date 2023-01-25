from __future__ import annotations

import asyncio
import os

from iambic.aws.models import (
    IAMBIC_HUB_ROLE_NAME,
    IAMBIC_SPOKE_ROLE_NAME,
    get_hub_role_arn,
)
from iambic.aws.utils import boto_crud_call, legacy_paginated_search
from iambic.core.logger import log

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


def get_iambic_spoke_role_template_body() -> str:
    template = f"{TEMPLATE_DIR}/IambicSpokeRole.yml"
    with open(template, "r") as f:
        return f.read()


async def create_stack(
    client, stack_name: str, template_body: str, parameters: list[dict], **kwargs
) -> bool:
    response = await boto_crud_call(
        client.create_stack,
        StackName=stack_name,
        TemplateBody=template_body,
        Parameters=parameters,
        OnFailure="ROLLBACK",
        **kwargs,
    )

    stack_id = response.get("StackId")
    resource_status = "CREATE_IN_PROGRESS"

    while resource_status == "CREATE_IN_PROGRESS":
        log.info("Waiting for stack to be created", stack_name=stack_name)
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
        log.error(
            "Unable to create AWS CloudFormation Stack",
            stack_name=stack_name,
            reason=stack_details.get("StackStatusReason"),
        )
        return False
    return True


async def create_stack_set(
    client,
    stack_set_name,
    template_body: str,
    parameters: list[dict],
    deployment_targets: dict,
    deployment_regions: list[str],
    **kwargs,
) -> bool:
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
            )
            await asyncio.sleep(30)
            continue
        elif all(
            instance.get("StackInstanceStatus", {}).get("DetailedStatus") == "SUCCEEDED"
            for instance in stack_instances
        ):
            return True
        else:
            failed_instances = [
                {
                    "Account": instance["Account"],
                    "Region": instance["Region"],
                    "Status": instance.get("StackInstanceStatus", {}).get(
                        "DetailedStatus"
                    ),
                    "StatusReason": instance.get("StatusReason"),
                }
                for instance in stack_instances
                if instance.get("StackInstanceStatus", {}).get("DetailedStatus")
                in ["FAILED", "CANCELLED"]
            ]
            log.error(
                "Unable to create stack set instances",
                stack_set_name=stack_set_name,
                failed_instances=failed_instances,
            )
            return False


async def create_change_detection_stacks(
    cf_client, org_id: str, org_account_id: str, role_arn: str = None
) -> bool:
    additional_kwargs = {"RoleARN": role_arn} if role_arn else {}
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
                    "ParameterValue": f"arn:aws:events:us-east-1:{org_account_id}:event-bus/IAMbicChangeDetectionEventBus",
                }
            ],
            Capabilities=["CAPABILITY_NAMED_IAM"],
            **additional_kwargs,
        )

    return stack_created


async def create_change_detection_stack_sets(
    cf_client, org_client, org_account_id: str
) -> bool:
    org_roots = await legacy_paginated_search(
        org_client.list_roots, response_key="Roots"
    )

    return await create_stack_set(
        cf_client,
        stack_set_name="IAMbicForwardEventRule",
        template_body=get_rule_forwarding_template_body(),
        parameters=[
            {
                "ParameterKey": "TargetEventBusArn",
                "ParameterValue": f"arn:aws:events:us-east-1:{org_account_id}:event-bus/IAMbicChangeDetectionEventBus",
            }
        ],
        deployment_targets={
            "OrganizationalUnitIds": [root["Id"] for root in org_roots],
            "AccountFilterType": "NONE",
        },
        deployment_regions=["us-east-1"],
        Capabilities=["CAPABILITY_NAMED_IAM"],
    )


async def create_iambic_eventbridge_stacks(
    cf_client, org_client, org_id: str, account_id: str, role_arn: str = None
) -> bool:
    successfully_created = await create_change_detection_stacks(
        cf_client, org_id, account_id, role_arn
    )
    if successfully_created:
        log.info(
            "Creating stack instances. "
            "You can check the progress here: https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacksets/IAMbicForwardEventRule/stacks\n"
            "WARNING: Don't Exit"
        )
        return await create_change_detection_stack_sets(
            cf_client, org_client, account_id
        )

    return successfully_created


async def create_spoke_role_stack_set(
    cf_client, org_client, hub_account_id: str
) -> bool:
    org_roots = await legacy_paginated_search(
        org_client.list_roots, response_key="Roots"
    )

    return await create_stack_set(
        cf_client,
        stack_set_name="IambicSpokeRole",
        template_body=get_iambic_spoke_role_template_body(),
        parameters=[
            {
                "ParameterKey": "HubRoleArn",
                "ParameterValue": get_hub_role_arn(hub_account_id),
            },
            {"ParameterKey": "SpokeRoleName", "ParameterValue": IAMBIC_SPOKE_ROLE_NAME},
        ],
        deployment_targets={
            "OrganizationalUnitIds": [root["Id"] for root in org_roots],
            "AccountFilterType": "NONE",
        },
        deployment_regions=["us-east-1"],
        Capabilities=["CAPABILITY_NAMED_IAM"],
    )


async def create_spoke_role_stack(
    cf_client, hub_account_id: str, role_arn: str = None
) -> bool:
    additional_kwargs = {"RoleARN": role_arn} if role_arn else {}

    return await create_stack(
        cf_client,
        stack_name="IambicSpokeRole",
        template_body=get_iambic_spoke_role_template_body(),
        parameters=[
            {
                "ParameterKey": "HubRoleArn",
                "ParameterValue": get_hub_role_arn(hub_account_id),
            },
            {"ParameterKey": "SpokeRoleName", "ParameterValue": IAMBIC_SPOKE_ROLE_NAME},
        ],
        Capabilities=["CAPABILITY_NAMED_IAM"],
        **additional_kwargs,
    )


async def create_hub_role_stack(
    cf_client, hub_account_id: str, assume_as_arn: str, role_arn: str = None
) -> bool:
    additional_kwargs = {"RoleARN": role_arn} if role_arn else {}
    stack_created = await create_stack(
        cf_client,
        stack_name="IambicHubRole",
        template_body=get_iambic_hub_role_template_body(),
        parameters=[
            {"ParameterKey": "HubRoleName", "ParameterValue": IAMBIC_HUB_ROLE_NAME},
            {"ParameterKey": "SpokeRoleName", "ParameterValue": IAMBIC_SPOKE_ROLE_NAME},
            {"ParameterKey": "AssumeAsArn", "ParameterValue": assume_as_arn},
        ],
        Capabilities=["CAPABILITY_NAMED_IAM"],
        **additional_kwargs,
    )
    if stack_created:
        return await create_spoke_role_stack(cf_client, hub_account_id, role_arn)

    return stack_created


async def create_iambic_role_stacks(
    cf_client,
    hub_account_id: str,
    assume_as_arn: str,
    role_arn: str = None,
    org_client=None,
) -> bool:
    hub_role_created = await create_hub_role_stack(
        cf_client, hub_account_id, assume_as_arn, role_arn
    )
    if hub_role_created and org_client:
        log.info(
            "Creating stack instances. "
            "You can check the progress here: https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacksets/CreateIambicSpokeRole/stacks\n"
            "WARNING: Don't Exit"
        )
        return await create_spoke_role_stack_set(cf_client, org_client, hub_account_id)

    return hub_role_created
