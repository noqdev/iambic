from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Optional, Union

import boto3
from botocore.exceptions import ClientError

from iambic.core.iambic_enum import IambicManaged
from iambic.core.logger import log
from iambic.core.utils import aio_wrapper, camel_to_snake

if TYPE_CHECKING:
    from iambic.core.models import ExecutionMessage
    from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig
    from iambic.plugins.v0_1_0.aws.models import AWSAccount


async def boto_crud_call(boto_fnc, **kwargs) -> Union[list, dict]:
    """Responsible for calls to boto. Adds async support and error handling
    :param boto_fnc:
    :param kwargs: The params to pass to the boto fnc
    :return:
    """
    retry_count = 0

    while True:
        try:
            return await aio_wrapper(boto_fnc, **kwargs)
        except ClientError as err:
            if "Throttling" in err.response["Error"]["Code"]:
                if retry_count >= 10:
                    raise
                retry_count += 1
                await asyncio.sleep(retry_count / 2)
                continue
            elif "AccessDenied" in err.response["Error"]["Code"]:
                raise
            else:
                raise


async def paginated_search(
    search_fnc,
    response_key: str = None,
    response_keys: list[str] = None,
    max_results: int = None,
    retain_key: bool = False,
    **search_kwargs,
) -> Union[list, dict]:
    """Retrieve and aggregate each paged response, returning a single list of each response object
    :param search_fnc:
    :param response_key:
    :param response_keys:
    :param max_results:
    :param retain_key: If true, the response_key will be retained in the response
    :return:
    """
    assert bool(response_key) ^ bool(response_keys)  # XOR

    if response_keys and not retain_key:
        log.warning("retain_key must be true if response_keys is provided")
        retain_key = True

    if response_key:
        response_keys = [response_key]

    results = {key: [] for key in response_keys}

    while True:
        response = await boto_crud_call(search_fnc, **search_kwargs)
        for response_key in response_keys:
            results[response_key].extend(response.get(response_key, []))

        if not response["IsTruncated"] or (max_results and len(results) >= max_results):
            return results if retain_key else results[response_key]
        else:
            search_kwargs["Marker"] = response["Marker"]


def get_identity_arn(caller_identity: dict) -> str:
    arn = caller_identity.get("Arn")
    if "sts" in arn:
        identity_arn_with_session_name = arn.replace(":sts:", ":iam:").replace(
            "assumed-role", "role"
        )
        return "/".join(identity_arn_with_session_name.split("/")[:-1])
    return arn


def get_current_role_arn(sts_client) -> str:
    return get_identity_arn(sts_client.get_caller_identity())


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
    is_first_call = True

    while True:
        response = await boto_crud_call(search_fnc, **search_kwargs)
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
    # cn_north_1 = "cn-north-1"


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


def is_valid_account_id(account_id: str):
    return bool(re.match(r"^\d{12}$", account_id))


async def remove_expired_resources(
    resource,
    template_resource_type: str,
    template_resource_id: str,
    delete_resource_if_expired: bool = True,
):
    from iambic.core.models import BaseModel

    if not isinstance(resource, BaseModel):
        return resource

    log_params = {}
    if hasattr(resource, "resource_type"):
        log_params["resource_type"] = resource.resource_type
    if hasattr(resource, "resource_id"):
        log_params["resource_id"] = resource.resource_id
    if template_resource_type != log_params.get(
        "resource_type"
    ) or template_resource_id != log_params.get("resource_id"):
        log_params["parent_resource_type"] = template_resource_type
        log_params["parent_resource_id"] = template_resource_id

    if isinstance(resource, BaseModel) and hasattr(resource, "expires_at"):
        if resource.expires_at:
            cur_time = datetime.now(tz=timezone.utc)
            if resource.expires_at < cur_time:
                log.info("Expired resource found, marking for deletion", **log_params)
                resource.deleted = True
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
            if delete_resource_if_expired:
                for elem in new_value:
                    if getattr(elem, "deleted", None) is True:
                        new_value.remove(elem)
                        setattr(resource, field_name, new_value)
        else:
            new_value = await remove_expired_resources(
                field_val, template_resource_type, template_resource_id
            )
            if getattr(new_value, "deleted", None) is True:
                setattr(resource, field_name, None)
            else:
                setattr(resource, field_name, new_value)

    return resource


async def set_org_account_variables(client, account: dict) -> dict:
    tags = await legacy_paginated_search(
        client.list_tags_for_resource, "Tags", ResourceId=account["Id"]
    )
    account["variables"] = [
        {"key": tag["Key"], "value": tag.get("Value")} for tag in tags
    ]
    return account


async def get_aws_account_map(config: AWSConfig) -> dict:
    """Returns a map containing all enabled account configs across all provided config instances

    :param config:
    :return: dict(account_id:str = AWSAccount)
    """
    aws_account_map = dict()
    for aws_account in config.accounts:
        if aws_account_map.get(aws_account.account_id):
            log.critical(
                "Account definition found in multiple configs",
                account_id=aws_account.account_id,
                account_name=aws_account.account_name,
            )
            raise ValueError
        elif aws_account.iambic_managed == IambicManaged.DISABLED:
            log.info(
                "IAMbic awareness disabled for the account. Skipping.",
                account_id=aws_account.account_id,
            )
            continue

        aws_account_map[aws_account.account_id] = aws_account

    return aws_account_map


async def create_assume_role_session(
    boto3_session,
    assume_role_arn: str,
    region_name: str,
    external_id: Optional[str] = None,
    session_name: str = "iambic",
) -> boto3.Session:
    if session_name is None:
        session_name = "iambic"
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


async def distribute_execution(aws_config: AWSConfig, exe_message: ExecutionMessage):
    tasks = []

    for account in aws_config.accounts:
        if account.identity_center_details:
            new_exe_message = exe_message.copy()
            new_exe_message.provider_id = account.account_id
            new_exe_message.metadata = {
                "service": "IdentityCenter",
                "region": account.identity_center_details.region,
            }
            tasks.append(new_exe_message)

        new_exe_message = exe_message.copy()
        new_exe_message.provider_id = account.account_id
        new_exe_message.metadata = {
            "service": "IAM",
            "region": RegionName.us_east_1.value,
        }
        tasks.append(new_exe_message)

    # execute tasks and check status
    # Aggregate results...or something?


async def account_execution(
    aws_accounts: list[AWSAccount], exe_message: ExecutionMessage
):
    tasks = []
    for account in aws_accounts:
        new_exe_message = exe_message.copy()
        new_exe_message.provider_id = account.account_id
        tasks.append(new_exe_message)

    # execute tasks and check status
    # Aggregate results...or something?
