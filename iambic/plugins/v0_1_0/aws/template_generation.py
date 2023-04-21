from typing import Union

from iambic.core.template_generation import (
    base_group_str_attribute as core_base_group_str_attribute,
)
from iambic.core.template_generation import (
    group_dict_attribute as core_group_dict_attribute,
)
from iambic.core.template_generation import (
    group_int_or_str_attribute as core_group_int_or_str_attribute,
)
from iambic.plugins.v0_1_0.aws.models import AWSAccount


async def base_group_str_attribute(
    aws_account_map: dict[str, AWSAccount], account_resources: list[dict]
) -> dict[str, list]:
    """Groups a string attribute by a shared name across aws_accounts

    Call group_int_or_str_attribute instead unless you need to transform this response.
    An example would be grouping role names for generating the template where you need to keep the file_path ref.
    :param aws_account_map: dict(account_id:str = AWSAccount)
    :param account_resources: list[dict(account_id:str, resources=list[dict(resource_val: str, **)])]
    :return: dict(attribute_val: str = list[dict(resource_val: str, account_id: str, **)])
    """

    return await core_base_group_str_attribute(
        aws_account_map, account_resources, "account_id"
    )


async def group_int_or_str_attribute(
    aws_account_map: dict[str, AWSAccount],
    number_of_accounts_resource_on: int,
    account_resources: Union[dict, list[dict]],
    key: Union[int, str],
) -> Union[int, str, list[dict]]:
    """Groups an attribute by aws_accounts, formats the attribute and normalizes the included aws_accounts.
    :param aws_account_map:
    :param number_of_accounts_resource_on:
    :param account_resources: dict(account_id: str = int_val) , list[dict(account_id:str, resources=list[dict])]
    :param key: Used to form the list[dict] response when there are multiple values for the attribute.
    :return:
    """

    return await core_group_int_or_str_attribute(
        aws_account_map,
        number_of_accounts_resource_on,
        account_resources,
        "account_id",
        "included_accounts",
        key,
    )


async def group_dict_attribute(
    aws_account_map: dict[str, AWSAccount],
    number_of_accounts_resource_on: int,
    account_resources: list[dict],
    is_dict_attr: bool = True,
    prefer_templatized: bool = False,
) -> Union[dict, list[dict]]:
    """Groups an attribute by aws_accounts, formats the attribute and normalizes the included aws_accounts.
    :param aws_account_map: {account_id: aws_account}
    :param number_of_accounts_resource_on:
    :param account_resources: list[dict(account_id:str, resources=list[dict])]
    :param is_dict_attr: If false and only one hit, still return as a list. Useful for things like inline_policies.
    :return:
    """

    return await core_group_dict_attribute(
        aws_account_map,
        number_of_accounts_resource_on,
        account_resources,
        "account_id",
        "included_accounts",
        is_dict_attr,
        prefer_templatized,
    )
