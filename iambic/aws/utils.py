import asyncio
import re
from datetime import datetime
from enum import Enum

from iambic.core.context import ExecutionContext
from iambic.core.logger import log
from iambic.core.utils import aio_wrapper, camel_to_snake


async def paginated_search(
    search_fnc, response_key: str, max_results: int = None, **search_kwargs
) -> list:
    """Retrieve and aggregate each paged response, returning a single list of each response object
    :param search_fnc:
    :param response_key:
    :param max_results:
    :return:
    """
    results = []

    while True:
        response = await aio_wrapper(search_fnc, **search_kwargs)
        results.extend(response.get(response_key, []))

        if not response["IsTruncated"] or (max_results and len(results) >= max_results):
            return results
        else:
            search_kwargs["Marker"] = response["Marker"]


class RegionName(Enum):
    us_east_1 = "us-east-1"
    us_west_1 = "us-west-1"
    us_west_2 = "us-west-2"
    eu_west_1 = "eu-west-1"
    eu_west_2 = "eu-west-2"
    eu_central_1 = "eu-central-1"
    ap_southeast_1 = "ap-southeast-1"
    ap_southeast_2 = "ap-southeast-2"
    ap_northeast_1 = "ap-northeast-1"
    ap_northeast_2 = "ap-northeast-2"
    sa_east_1 = "sa-east-1"
    cn_north_1 = "cn-north-1"


def normalize_boto3_resp(obj):
    skip_formatting_for = ["condition"]
    if isinstance(obj, dict):
        new_obj = dict()
        for k, v in obj.items():
            k = camel_to_snake(k)
            if isinstance(v, list):
                new_obj[k] = [normalize_boto3_resp(x) for x in v]
            else:
                new_obj[k] = (
                    normalize_boto3_resp(v) if k not in skip_formatting_for else v
                )
        return new_obj
    elif isinstance(obj, list):
        return [normalize_boto3_resp(x) for x in obj]
    else:
        return obj


def get_closest_value(matching_values: list, aws_account):
    if len(matching_values) == 1:
        return matching_values[0]

    account_value_hit = dict(returns=None, specificty=0)

    account_ids = [aws_account.account_id]
    if account_name := aws_account.account_name:
        account_ids.append(account_name.lower())

    for matching_value in matching_values:
        resource_accounts = sorted(matching_value.included_accounts, key=len)
        for resource_account in resource_accounts:
            for account_id in account_ids:
                if resource_account == "*" and account_value_hit["specificty"] == 0:
                    account_value_hit = {"returns": matching_value, "specificty": 1}
                elif re.match(resource_account.lower(), account_id) and len(
                    resource_account
                ) > account_value_hit.get("specificty", 0):
                    account_value_hit = {
                        "returns": matching_value,
                        "specificty": len(resource_account),
                    }
                    break

    return account_value_hit["returns"]


def evaluate_on_account(resource, aws_account, context: ExecutionContext) -> bool:
    from iambic.aws.models import AccessModel

    if context.execute and (
        aws_account.read_only or getattr(resource, "read_only", False)
    ):
        return False
    if not issubclass(type(resource), AccessModel):
        return True

    if aws_account.org_id:
        if aws_account.org_id in resource.excluded_orgs:
            return False
        elif not any(
            re.match(org_id, aws_account.org_id) for org_id in resource.included_orgs
        ):
            return False

    account_ids = [aws_account.account_id]
    if account_name := aws_account.account_name:
        account_ids.append(account_name.lower())

    for account_id in account_ids:
        if any(
            re.match(resource_account.lower(), account_id)
            for resource_account in resource.excluded_accounts
        ):
            return False

    for account_id in account_ids:
        if any(
            resource_account == "*" for resource_account in resource.included_accounts
        ):
            return True
        elif any(
            re.match(resource_account.lower(), account_id)
            for resource_account in resource.included_accounts
        ):
            return True

    return False


def apply_to_account(resource, aws_account, context: ExecutionContext) -> bool:
    from iambic.aws.models import Deleted

    if hasattr(resource, "deleted"):
        deleted_resource_type = isinstance(resource, Deleted)

        if isinstance(resource.deleted, bool):
            if resource.deleted and not deleted_resource_type:
                return False
        else:
            deleted_obj = resource.get_attribute_val_for_account(aws_account, "deleted")
            deleted_obj = get_closest_value(deleted_obj, aws_account)
            if deleted_obj and deleted_obj.deleted and not deleted_resource_type:
                return False

    return evaluate_on_account(resource, aws_account, context)


async def remove_expired_resources(
    resource, template_resource_type: str, template_resource_id: str
):
    from iambic.core.models import BaseModel

    if (
        not issubclass(type(resource), BaseModel)
        or not hasattr(resource, "expires_at")
        or getattr(resource, "deleted", None)
    ):
        return resource

    log_params = dict(
        resource_type=resource.resource_type, resource_id=resource.resource_id
    )
    if (
        template_resource_type != resource.resource_type
        or template_resource_id != resource.resource_id
    ):
        log_params["parent_resource_type"] = template_resource_type
        log_params["parent_resource_id"] = template_resource_id

    if hasattr(resource, "expires_at") and resource.expires_at:
        if resource.expires_at < datetime.utcnow():
            resource.deleted = True
            log.info("Expired resource found, marking for deletion", **log_params)
            return resource

    for field_name in resource.__fields__.keys():
        field_val = getattr(resource, field_name)
        if isinstance(field_val, list):
            resource.__fields__[field_name] = await asyncio.gather(
                *[
                    remove_expired_resources(
                        elem, template_resource_type, template_resource_id
                    )
                    for elem in field_val
                ]
            )
        else:
            resource.__fields__[field_name] = await remove_expired_resources(
                field_val, template_resource_type, template_resource_id
            )

    return resource


def get_aws_account_map(configs: list) -> dict:
    """Returns a map containing all account configs across all provided config instances

    :param configs:
    :return: dict(account_id:str = AWSAccount)
    """
    aws_account_map = dict()
    for config in configs:
        config.set_account_defaults()
        for aws_account in config.aws_accounts:
            if aws_account_map.get(aws_account.account_id):
                log.critical(
                    "Account definition found in multiple configs",
                    account_id=aws_account.account_id,
                    account_name=aws_account.account_name,
                )
                raise ValueError
            aws_account_map[aws_account.account_id] = aws_account

    return aws_account_map
