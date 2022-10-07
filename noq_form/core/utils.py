import asyncio
import re
from datetime import datetime
from io import StringIO

from asgiref.sync import sync_to_async
from ruamel.yaml import YAML

from noq_form.core.logger import log


def camel_to_snake(str_obj: str) -> str:
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", str_obj).lower()


def camel_to_kebab(str_obj: str) -> str:
    return re.sub("([a-z0-9])([A-Z])", r"\1-\2", str_obj).lower()


def snake_to_camelback(str_obj: str) -> str:
    return re.sub(r"_([a-z])", lambda x: x.group(1).upper(), str_obj)


def snake_to_camelcap(str_obj: str) -> str:
    str_obj = camel_to_snake(
        str_obj
    ).title()  # normalize string and add required case convention
    return str_obj.replace("_", "")  # Remove underscores


def get_closest_value(matching_values: list, account_config):
    if len(matching_values) == 1:
        return matching_values[0]

    account_value_hit = dict(returns=None, specificty=0)

    account_ids = [account_config.account_id]
    if account_name := account_config.account_name:
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


def evaluate_on_account(resource, account_config) -> bool:
    from noq_form.core.models import AccessModel

    if not issubclass(type(resource), AccessModel):
        return True

    if account_config.org_id:
        if account_config.org_id in resource.excluded_orgs:
            return False
        elif not any(
            re.match(org_id, account_config.org_id) for org_id in resource.included_orgs
        ):
            return False

    account_ids = [account_config.account_id]
    if account_name := account_config.account_name:
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


def apply_to_account(resource, account_config) -> bool:

    if hasattr(resource, "enabled"):
        if isinstance(resource.enabled, bool):
            if not resource.enabled:
                return False
        else:
            enabled_obj = resource.get_attribute_val_for_account(
                account_config, "enabled"
            )
            enabled_obj = get_closest_value(enabled_obj, account_config)
            if not enabled_obj.enabled:
                return False

    return evaluate_on_account(resource, account_config)


async def remove_expired_resources(
    resource, template_resource_type: str, template_resource_name: str
):
    from noq_form.core.models import BaseModel

    if (
        not issubclass(type(resource), BaseModel)
        or not hasattr(resource, "expires_at")
        or getattr(resource, "enabled", None) is False
    ):
        return resource

    log_params = dict(
        resource_type=resource.resource_type, resource_name=resource.resource_name
    )
    if (
        template_resource_type != resource.resource_type
        or template_resource_name != resource.resource_name
    ):
        log_params["parent_resource_type"] = template_resource_type
        log_params["parent_resource_name"] = template_resource_name

    if hasattr(resource, "expires_at") and resource.expires_at:
        if resource.expires_at < datetime.utcnow():
            resource.enabled = False
            log.info("Expired resource found, marking for deletion", **log_params)
            return resource

    for field_name in resource.__fields__.keys():
        field_val = getattr(resource, field_name)
        if isinstance(field_val, list):
            resource.__fields__[field_name] = await asyncio.gather(
                *[
                    remove_expired_resources(
                        elem, template_resource_type, template_resource_name
                    )
                    for elem in field_val
                ]
            )
        else:
            resource.__fields__[field_name] = await remove_expired_resources(
                field_val, template_resource_type, template_resource_name
            )

    return resource


def gather_templates() -> list[str]:
    """
    Get pwd
    Traverse all directories to get all yamls.
    Return the path for each yaml with template_type: NOQ::.*
    """
    ...


async def aio_wrapper(fnc, *args, **kwargs):
    thread_sensitive = kwargs.pop("thread_sensitive", False)
    return await sync_to_async(fnc, thread_sensitive=thread_sensitive)(*args, **kwargs)


class NoqYaml(YAML):
    def dump(self, data, stream=None, **kw):
        inefficient = False
        if stream is None:
            inefficient = True
            stream = StringIO()
        YAML.dump(self, data, stream, **kw)
        if inefficient:
            return stream.getvalue()


typ = "rt"
yaml = NoqYaml(typ=typ)
