import json
from typing import Optional

from botocore.exceptions import ClientError

from iambic.aws.utils import paginated_search
from iambic.core.utils import NoqSemaphore, aio_wrapper


async def get_resource(
    resource_identifier: str, resource_type: str, cloudcontrol_client, **kwargs
) -> Optional[dict]:
    try:
        resource_details = await aio_wrapper(
            cloudcontrol_client.get_resource,
            TypeName=resource_type,
            Identifier=resource_identifier,
        )

        resource_details["ResourceDescription"]["Properties"] = json.loads(
            resource_details["ResourceDescription"]["Properties"]
        )
        del resource_details["ResponseMetadata"]
        return resource_details
    except ClientError:
        raise


async def list_resources(
    cloudcontrol_client,
    supported_resource_types: list[dict[str, str]],
):
    collected_resources = []
    get_cloud_control_semaphore = NoqSemaphore(get_resource, 50)
    for resource_type in supported_resource_types:
        cloudcontrol_response = await paginated_search(
            cloudcontrol_client.list_resources,
            "ResourceDescriptions",
            TypeName=resource_type.get("type"),
            ResourceModel=resource_type.get("ResourceModel"),
        )
        resource_identifiers = []
        for resource in cloudcontrol_response:
            resource_identifiers.append(resource["Identifier"])
        resource_details = await get_cloud_control_semaphore.process(
            [
                {
                    "resource_identifier": resource_identifier,
                    "resource_type": resource_type,
                    "cloudcontrol_client": cloudcontrol_client,
                }
                for resource_identifier in resource_identifiers
            ]
        )
        collected_resources.extend(resource_details)
    return collected_resources
