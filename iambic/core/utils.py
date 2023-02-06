from __future__ import annotations

import asyncio
import contextlib
import glob
import os
import pathlib
import re
from datetime import datetime
from io import StringIO
from typing import Any, Union
from urllib.parse import unquote_plus

import aiofiles
from asgiref.sync import sync_to_async
from ruamel.yaml import YAML

from iambic.core import noq_json as json

NOQ_TEMPLATE_REGEX = r".*template_type:\n?.*NOQ::"


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


async def resource_file_upsert(
    file_path: Union[str, pathlib.Path],
    content_as_dict: dict,
    replace_file: bool = False,
):
    if (
        not replace_file
        and os.path.exists(file_path)
        and os.stat(file_path).st_size != 0
    ):
        async with aiofiles.open(file_path, mode="r") as f:
            content_dict = json.loads(await f.read())
            content_as_dict = {**content_dict, **content_as_dict}

    async with aiofiles.open(file_path, mode="w") as f:
        await f.write(json.dumps(content_as_dict, indent=2))


async def file_regex_search(file_path: str, re_pattern: str) -> Union[str, None]:
    async with aiofiles.open(file_path, mode="r") as f:
        file_content = await f.read()
        if re.search(re_pattern, file_content):
            return file_path


async def gather_templates(repo_dir: str, template_type: str = None) -> list[str]:
    if template_type and template_type.startswith("NOQ::"):
        # Strip the prefix so it plays nice with NOQ_TEMPLATE_REGEX
        template_type = template_type.replace("NOQ::", "")

    regex_pattern = (
        rf"{NOQ_TEMPLATE_REGEX}.*{template_type}"
        if template_type
        else NOQ_TEMPLATE_REGEX
    )
    # Support both yaml and yml extensions for templates
    file_paths = glob.glob(f"{repo_dir}/**/*.yaml", recursive=True)
    file_paths += glob.glob(f"{repo_dir}*.yaml", recursive=True)
    file_paths += glob.glob(f"{repo_dir}/**/*.yml", recursive=True)
    file_paths += glob.glob(f"{repo_dir}*.yml", recursive=True)
    file_paths = await asyncio.gather(
        *[file_regex_search(fp, regex_pattern) for fp in file_paths]
    )
    return [fp for fp in file_paths if fp]


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


class NoqSemaphore:
    def __init__(
        self, callback_function: any, batch_size: int, callback_is_async: bool = True
    ):
        """Makes a reusable semaphore that wraps a provided function.
        Useful for batch processing things that could be rate limited.

        Example prints hello there 3 times in quick succession, waits 3 seconds then processes another 3:
            from datetime import datetime

            async def hello_there():
                print(f"Hello there - {datetime.utcnow()}")
                await asyncio.sleep(3)

            hello_there_semaphore = NoqSemaphore(hello_there, 3)
            asyncio.run(hello_there_semaphore.process([{} for _ in range(10)]))
        """
        self.limit = asyncio.Semaphore(batch_size)
        self.callback_function = callback_function
        self.callback_is_async = callback_is_async

    async def handle_message(self, **kwargs):
        async with self.limit:
            if self.callback_is_async:
                return await self.callback_function(**kwargs)

            return await aio_wrapper(self.callback_function, **kwargs)

    async def process(self, messages: list[dict], return_exceptions=False):
        return await asyncio.gather(
            *[asyncio.create_task(self.handle_message(**msg)) for msg in messages],
            return_exceptions=return_exceptions,
        )


async def async_batch_processor(
    tasks: list,
    batch_size: int,
    seconds_between_process: int = 1,
    return_exceptions: bool = False,
) -> list:
    """
    Batches up tasks in an effort to prevent rate limiting
    """
    if len(tasks) <= batch_size:
        return await asyncio.gather(*tasks, return_exceptions=return_exceptions)

    response = []
    for min_elem in range(0, len(tasks), batch_size):
        response.extend(
            await asyncio.gather(
                *tasks[min_elem : min_elem + batch_size],
                return_exceptions=return_exceptions,
            )
        )
        if len(response) == len(tasks):
            return response

        await asyncio.sleep(seconds_between_process)

    return response


def un_wrap_json(json_obj: Any) -> Any:
    """Helper function to unwrap nested JSON in the AWS Config resource configuration."""
    # pylint: disable=C0103,W0703,R0911
    # Is this a field that we can safely return?
    if isinstance(json_obj, (type(None), int, bool, float)):  # noqa
        return json_obj
    # Is this a Datetime? Convert it to a string and return it:
    if isinstance(json_obj, datetime):
        return str(json_obj)
    # Is this a Dictionary?
    if isinstance(json_obj, dict):
        decoded = {k: un_wrap_json(v) for k, v in json_obj.items()}
    elif isinstance(json_obj, list):
        decoded = [un_wrap_json(x) for x in json_obj]
        # Yes, try to sort the contents of lists. This is because AWS does not consistently store list ordering for many resource types:
        with contextlib.suppress(Exception):
            sorted_list = sorted(decoded)
            decoded = sorted_list
    else:
        # Try to load the JSON string:
        try:
            # Check if the string starts with a "[" or a "{" (because apparently '123' is a valid JSON)
            for check_field in {
                "{",
                "[",
                '"{',
                '"[',
            }:  # Some of the double-wrapping is really ridiculous
                if json_obj.startswith(check_field):
                    decoded = json.loads(json_obj)
                    # If we loaded this properly, then we need to pass the decoded JSON back in for all the nested stuff:
                    return un_wrap_json(decoded)
            # Check if this string is URL Encoded - if it is, then re-run it through:
            decoded = unquote_plus(json_obj)
            return un_wrap_json(decoded) if decoded != json_obj else json_obj
        except Exception:  # noqa
            return json_obj
    return decoded


def un_wrap_json_and_dump_values(json_obj: Any) -> Any:
    json_obj = un_wrap_json(json_obj)
    for k, v in json_obj.items():
        json_obj[k] = json.dumps(v)
    return json_obj


# lifted from cloudumi's repo common.lib.generic import sort_dict, and modified to support prioritization
def sort_dict(original, prioritize=None):
    """Recursively sorts dictionary keys and dictionary values in alphabetical order,
    with optional prioritization of certain elements.
    """
    if prioritize is None:
        prioritize = [
            "template_type",
            "name",
            "description",
            "included_accounts",
            "excluded_accounts",
        ]
    if isinstance(original, dict):
        # Make a new "ordered" dictionary. No need for Collections in Python 3.7+
        # Sort the keys in the dictionary
        keys = sorted(original.keys())
        # Move the keys in the prioritized list to the front
        keys = [k for k in prioritize if k in keys] + [
            k for k in keys if k not in prioritize
        ]
        d = {k: v for k, v in [(k, original[k]) for k in keys]}
    else:
        d = original
    for k in d:
        if isinstance(d[k], str):
            continue
        if isinstance(d[k], list) and len(d[k]) > 1 and isinstance(d[k][0], str):
            d[k] = sorted(d[k])
        if isinstance(d[k], dict):
            d[k] = sort_dict(d[k], prioritize)
        if isinstance(d[k], list) and len(d[k]) >= 1 and isinstance(d[k][0], dict):
            for i in range(len(d[k])):
                d[k][i] = sort_dict(d[k][i], prioritize)
    return d


def transform_commments(yaml_dict):

    comment_dict = {}
    yaml_dict["metadata_commented_dict"] = comment_dict
    for key, comment in yaml_dict.ca.items.items():
        comment_dict[key] = comment[2].value
        value = yaml_dict[key]
        if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
            yaml_dict[key] = [transform_commments(n) for n in value]
        elif isinstance(value, dict):
            yaml_dict[key] = transform_commments(value)
    return yaml_dict


def create_commented_map(_dict: dict):
    from ruamel.yaml import CommentedMap

    commented_map = CommentedMap()
    index = 0
    comment_key_to_comment = _dict.pop("metadata_commented_dict", {})
    for key, value in _dict.items():
        if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
            value = [create_commented_map(n) for n in value]
        elif isinstance(value, dict):
            value = create_commented_map(value)
        commented_map.insert(index, key, value, comment_key_to_comment.get(key, None))
        index = index + 1
    return commented_map


typ = "rt"
yaml = NoqYaml(typ=typ)
yaml.preserve_quotes = True
yaml.indent(mapping=2, sequence=4, offset=2)
yaml.representer.ignore_aliases = lambda *data: True
yaml.width = 4096
