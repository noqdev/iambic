from __future__ import annotations

import asyncio
import re
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional, Union

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from iambic.core.iambic_enum import IambicManaged
from iambic.core.logger import log
from iambic.core.utils import aio_wrapper, is_regex_match

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig, ImportAction


async def process_import_rules(
    config: AWSConfig,
    template_type: str,
    identifier: str,
    tags: list[dict[str, str]],
    resource_dict: dict[str, Any],
) -> list[ImportAction]:
    actions = []

    for rule in config.import_rules:
        # Initialize match indicators
        tag_match = name_match = path_match = template_type_match = False

        # Match by tag
        if rule.match_tags:
            for tag in rule.match_tags:
                for resource_tag in tags:
                    if is_regex_match(tag.key, resource_tag.get("key")) and (
                        tag.value is None
                        or is_regex_match(tag.value, resource_tag.get("value"))
                    ):
                        tag_match = True
                        break

        # Match by name/identifier
        if rule.match_names:
            for pattern in rule.match_names:
                if is_regex_match(pattern, identifier):
                    name_match = True
                    break

        # Match by path
        if rule.match_paths:
            for pattern in rule.match_paths:
                if is_regex_match(pattern, resource_dict.get("path", "")):
                    path_match = True
                    break

        # Match by template type
        if rule.match_template_types:
            for pattern in rule.match_template_types:
                if is_regex_match(pattern, template_type):
                    template_type_match = True
                    break

        # Add action to the list if all conditions specified in the rule are satisfied
        if (
            (not rule.match_tags or tag_match)
            and (not rule.match_names or name_match)
            and (not rule.match_paths or path_match)
            and (not rule.match_template_types or template_type_match)
        ):
            actions.append(rule.action)
    return actions


def calculate_import_preference(existing_template):
    prefer_templatized = False
    try:
        if existing_template:
            # this is expensive just to compute if
            # the existing template is already bias toward templatized.
            existing_template_in_str = existing_template.json()
            prefer_templatized = "{{" in existing_template_in_str
    except Exception as exc_info:
        # We are willing to tolerate exception because
        # we are calculating preference from possibly bad templates on disk
        log_params = {"exc_info": str(exc_info)}
        log.error("cannot calculate preference from existing template", **log_params)
    return prefer_templatized


async def boto_crud_call(
    boto_fnc, retryable_errors: list = None, **kwargs
) -> Union[list, dict]:
    """Responsible for calls to boto. Adds async support and error handling
    :param boto_fnc:
    :param retryable_errors: A list of error codes that should be retried
    :param kwargs: The params to pass to the boto fnc
    :return:
    """
    max_attempts = 20
    retry_count = 0
    always_retryable_errors = ["Throttling", "TooManyRequestsException"]
    if retryable_errors:
        retryable_errors.extend(always_retryable_errors)
    else:
        retryable_errors = always_retryable_errors

    while True:
        try:
            return await aio_wrapper(boto_fnc, **kwargs)
        except ClientError as err:
            error_code = err.response["Error"]["Code"]
            if any(retryable_err in error_code for retryable_err in retryable_errors):
                if retry_count >= max_attempts:
                    raise
                retry_count += 1
                log.info(
                    f"{error_code} error",
                    provider="aws",
                    api_call=boto_fnc.__name__,
                    remaining_retries=max_attempts - retry_count,
                )
                await asyncio.sleep(min(retry_count / 4, 3))
                continue
            elif "AccessDenied" in err.response["Error"]["Code"]:
                raise
            else:
                raise
        except NoCredentialsError as exc:
            log.error(
                f"Unable to create an AWS session, you may need to run `aws configure` or export your AWS_PROFILE; err={exc}"
            )
            raise RuntimeError(
                f"Unable to create an AWS session, you may need to run `aws configure` or export your AWS_PROFILE; err={exc}"
            )


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

        if not response.get("IsTruncated") or (
            max_results and len(results) >= max_results
        ):
            return results if retain_key else results[response_key]
        else:
            search_kwargs["Marker"] = response["Marker"]


def get_identity_arn(caller_identity: dict) -> str:
    arn = caller_identity.get("Arn")
    arn_split_by_colon = arn.split(":")
    resource_path_split_by_slash = []
    maybe_assumed_role = ""
    role_name = ""

    if len(arn_split_by_colon) < 6:
        # magic number 6 is the expected number of parts for sts caller identity arn
        # https://docs.aws.amazon.com/IAM/latest/UserGuide/reference-arns.html
        return arn

    resource_path_split_by_slash = arn_split_by_colon[5].split("/")

    if len(resource_path_split_by_slash) < 2:
        # magic number 2 is from the format of assumed-role/role-name/role-session-name format
        return arn

    maybe_assumed_role = resource_path_split_by_slash[0]
    role_name = resource_path_split_by_slash[1]

    if maybe_assumed_role != "assumed-role":
        # for example, user-like arn
        return arn

    if maybe_assumed_role == "assumed-role" and role_name.startswith("AWSReservedSSO_"):
        return arn

    # We attempt to derived IAM role principals from Assumed-role session principals
    # AWS Identity Center generated roles can have a path that is under path
    # aws-reserved/sso.amazonaws.com/us-west-2/
    # Path information is not contained within the caller_identity dictionary
    # In the event if we see prefix with AWSReservedSSO_, we fall back to
    # assumed-role session principals
    # See https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_principal.html#Principal_specifying
    identity_arn_with_session_name = arn.replace(":sts:", ":iam:").replace(
        "assumed-role", "role"
    )
    return "/".join(identity_arn_with_session_name.split("/")[:-1])


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
    af_south_1 = "af-south-1"
    ap_east_1 = "ap-east-1"
    ap_northeast_1 = "ap-northeast-1"
    ap_northeast_2 = "ap-northeast-2"
    ap_northeast_3 = "ap-northeast-3"
    ap_south_1 = "ap-south-1"
    ap_south_2 = "ap-south-2"
    ap_southeast_1 = "ap-southeast-1"
    ap_southeast_2 = "ap-southeast-2"
    ap_southeast_3 = "ap-southeast-3"
    ap_southeast_4 = "ap-southeast-4"
    ca_central_1 = "ca-central-1"
    cn_north_1 = "cn-north-1"
    cn_northwest_1 = "cn-northwest-1"
    eu_central_1 = "eu-central-1"
    eu_central_2 = "eu-central-2"
    eu_north_1 = "eu-north-1"
    eu_south_1 = "eu-south-1"
    eu_south_2 = "eu-south-2"
    eu_west_1 = "eu-west-1"
    eu_west_2 = "eu-west-2"
    eu_west_3 = "eu-west-3"
    il_central_1 = "il-central-1"
    me_central_1 = "me-central-1"
    me_south_1 = "me-south-1"
    sa_east_1 = "sa-east-1"
    us_east_1 = "us-east-1"
    us_east_2 = "us-east-2"
    us_gov_east_1 = "us-gov-east-1"
    us_gov_west_1 = "us-gov-west-1"
    us_west_1 = "us-west-1"
    us_west_2 = "us-west-2"


def is_valid_account_id(account_id: str):
    return bool(re.match(r"^\d{12}$", account_id))


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
        raise


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
