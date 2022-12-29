import asyncio
import re
from datetime import datetime
from enum import Enum
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from iambic.core.context import ExecutionContext
from iambic.core.logger import log
from iambic.core.utils import aio_wrapper, camel_to_snake


async def paginated_search(
    search_fnc,
    response_key: str,
    max_results: int = None,
    retain_key: bool = False,
    **search_kwargs,
) -> list:
    """Retrieve and aggregate each paged response, returning a single list of each response object
    :param search_fnc:
    :param response_key:
    :param max_results:
    :param retain_key: If true, the response_key will be retained in the response
    :return:
    """
    results = []
    retry_count = 0

    while True:
        try:
            response = await aio_wrapper(search_fnc, **search_kwargs)
        except ClientError as err:
            if "Throttling" in err.response["Error"]["Code"]:
                if retry_count >= 10:
                    raise
                retry_count += 1
                await asyncio.sleep(retry_count * 2)
                continue
            else:
                raise

        retry_count = 0
        results.extend(response.get(response_key, []))

        if not response["IsTruncated"] or (max_results and len(results) >= max_results):
            return {response_key: results} if retain_key else results
        else:
            search_kwargs["Marker"] = response["Marker"]


async def legacy_paginated_search(
    search_fnc,
    response_key: str,
    max_results: int = None,
    retain_key: bool = False,
    **search_kwargs,
) -> list:
    """Retrieve and aggregate each paged response, returning a single list of each response object

    Why is there 2 paginated searches? - AWS has 2 ways of paginating results
    This one seems to be the older way which is why it's called legacy

    :param search_fnc:
    :param response_key:
    :param max_results:
    :param retain_key: If true, the response_key will be retained in the response
    :return:
    """
    results = []
    retry_count = 0
    is_first_call = True

    while True:
        try:
            response = await aio_wrapper(search_fnc, **search_kwargs)
        except ClientError as err:
            if "Throttling" in err.response["Error"]["Code"]:
                if retry_count >= 10:
                    raise
                retry_count += 1
                await asyncio.sleep(retry_count * 2)
                continue
            else:
                log.warning(err.response["Error"]["Code"])
                raise

        retry_count = 0
        results.extend(response.get(response_key, []))

        if (
            not response.get("NextToken")
            or (max_results and len(results) >= max_results)
            or (not results and not is_first_call)
        ):
            return {response_key: results} if retain_key else results
        else:
            is_first_call = False
            search_kwargs["NextToken"] = response["NextToken"]


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


def get_account_value(matching_values: list, account_id: str, account_name: str = None):
    account_reprs = [account_id]
    if account_name:
        account_reprs.append(account_name.lower())

    included_account_map = dict()
    included_account_lists = list()

    for matching_val in matching_values:
        for included_account in matching_val.included_accounts:
            included_account_map[included_account] = matching_val
            included_account_lists.append(included_account)

    for included_account in sorted(included_account_lists, key=len, reverse=True):
        cur_val = included_account_map[included_account]
        if any(
            any(
                re.match(excluded_account.lower(), account_repr)
                for account_repr in account_reprs
            )
            for excluded_account in cur_val.excluded_accounts
        ):
            log.debug("Hit an excluded account rule", account_id=account_id)
            continue
        elif included_account == "*" or any(
            re.match(included_account.lower(), account_repr)
            for account_repr in account_reprs
        ):
            return cur_val


def evaluate_on_account(resource, aws_account, context: ExecutionContext) -> bool:
    from iambic.aws.models import AccessModel

    if aws_account.read_only or getattr(resource, "read_only", False):
        return False

    # SSO Models don't inherit from AccessModel and rely only on included/excluded orgs.
    # hasattr is how we are currently handling this special case.
    if not issubclass(type(resource), AccessModel) and not hasattr(
        resource, "included_orgs"
    ):
        return True

    if aws_account.org_id:
        if aws_account.org_id in resource.excluded_orgs:
            return False
        elif "*" not in resource.included_orgs and not any(
            re.match(org_id, aws_account.org_id) for org_id in resource.included_orgs
        ):
            return False

    if not hasattr(resource, "included_accounts"):
        return True

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
            deleted_obj = get_account_value(
                deleted_obj, aws_account.account_id, aws_account.account_name
            )
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
            new_value = await asyncio.gather(
                *[
                    remove_expired_resources(
                        elem, template_resource_type, template_resource_id
                    )
                    for elem in field_val
                ]
            )
            setattr(resource, field_name, new_value)
        else:
            new_value = await remove_expired_resources(
                field_val, template_resource_type, template_resource_id
            )
            setattr(resource, field_name, new_value)

    return resource


async def set_org_account_variables(client, account: dict) -> dict:
    tags = await legacy_paginated_search(
        client.list_tags_for_resource, "Tags", ResourceId=account["Id"]
    )
    account["variables"] = [{"key": tag["Key"], "value": tag["Value"]} for tag in tags]
    return account


async def get_aws_account_map(configs: list) -> dict:
    """Returns a map containing all account configs across all provided config instances

    :param configs:
    :return: dict(account_id:str = AWSAccount)
    """
    aws_account_map = dict()
    for config in configs:
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


async def create_assume_role_session(
    boto3_session,
    assume_role_arn: str,
    region_name: str,
    external_id: Optional[str] = None,
    session_name: str = "iambic",
) -> boto3.Session:
    try:
        sts = boto3_session.client(
            "sts",
            endpoint_url=f"https://sts.{region_name}.amazonaws.com",
            region_name=region_name,
        )
        role_params = dict(RoleArn=assume_role_arn, RoleSessionName=session_name)
        if external_id:
            role_params["ExternalId"] = external_id
        role = await aio_wrapper(sts.assume_role, **role_params)
        return boto3.Session(
            region_name=region_name,
            aws_access_key_id=role["Credentials"]["AccessKeyId"],
            aws_secret_access_key=role["Credentials"]["SecretAccessKey"],
            aws_session_token=role["Credentials"]["SessionToken"],
        )
    except Exception as err:
        log.error("Failed to assume role", assume_role_arn=assume_role_arn, error=err)


def boto3_retry(f):
    async def wrapper(*args, **kwargs):
        max_retries = kwargs.pop("max_retries", 10)
        for attempt in range(max_retries):
            try:
                return await f(*args, **kwargs)
            except ClientError as err:
                if (
                    err.response["Error"]["Code"] == "Throttling"
                    and attempt < max_retries - 1
                ):
                    await asyncio.sleep(1)
                else:
                    raise

    return wrapper
