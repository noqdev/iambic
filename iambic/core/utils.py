from __future__ import annotations

import asyncio
import contextlib
import glob
import os
import pathlib
import re
import sys
import tempfile
import typing
from datetime import datetime
from io import StringIO
from typing import TYPE_CHECKING, Any, Coroutine, Optional, Union
from urllib.parse import unquote_plus

import aiofiles
from asgiref.sync import sync_to_async
from iambic.core import noq_json as json
from iambic.core.context import ExecutionContext
from iambic.core.exceptions import RateLimitException
from iambic.core.iambic_enum import IambicManaged
from iambic.core.logger import log
from ruamel.yaml import YAML

if TYPE_CHECKING:
    from iambic.core.models import ProposedChange


NOQ_TEMPLATE_REGEX = r".*template_type:\n?.*NOQ::"
RATE_LIMIT_STORAGE: dict[str, int] = {}

__WRITABLE_DIRECTORY__ = pathlib.Path.home()


def init_writable_directory() -> None:
    if os.environ.get("AWS_LAMBDA_FUNCTION_NAME", False):
        temp_writable_directory = tempfile.mkdtemp(prefix="lambda")
        __WRITABLE_DIRECTORY__ = pathlib.Path(temp_writable_directory)
    else:
        __WRITABLE_DIRECTORY__ = pathlib.Path.home()

    this_module = sys.modules[__name__]
    setattr(this_module, "__WRITABLE_DIRECTORY__", __WRITABLE_DIRECTORY__)


def get_writable_directory() -> pathlib.Path:
    return __WRITABLE_DIRECTORY__


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


async def plugin_apply_wrapper(
    apply_awaitable: Coroutine, proposed_changes: list[ProposedChange]
) -> list[ProposedChange]:
    exceptions = []
    try:
        await apply_awaitable
    except Exception as e:
        exceptions.append(str(e))
    for change in proposed_changes:
        change.exceptions_seen = exceptions
    return proposed_changes


async def resource_file_upsert(
    file_path: Union[str, pathlib.Path],
    content_as_dict: dict,
    replace_file: bool = False,
):
    """
    Update or create a resource file with the given content.

    This function updates or creates a resource file at the given file path with the given content, which is
    represented as a dictionary. If the file already exists and `replace_file` is False, the function merges
    the existing content with the new content. If `replace_file` is True, the function overwrites the file
    with the new content.

    Args:
    - file_path (Union[str, pathlib.Path]): The file path for the resource file.
    - content_as_dict (dict): The content to be written to the resource file, represented as a dictionary.
    - replace_file (bool, optional): A flag indicating whether to replace the file if it already exists.
        Default is False.

    Returns:
    - None
    """
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
        # Strip the prefix, so it plays nice with NOQ_TEMPLATE_REGEX
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


def transform_comments(yaml_dict):

    comment_dict = {}
    yaml_dict["metadata_commented_dict"] = comment_dict
    for key, comment in yaml_dict.ca.items.items():
        comment_dict[key] = comment[2].value
        value = yaml_dict[key]
        if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
            yaml_dict[key] = [transform_comments(n) for n in value]
        elif isinstance(value, dict):
            yaml_dict[key] = transform_comments(value)
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


def evaluate_on_provider(
    resource,
    provider_details,
    context: ExecutionContext,
    exclude_import_only: bool = True,
) -> bool:
    """
    Determine if the provided resource is on or should be on the given provider.

    This function takes a resource, provider details, and an execution context, and returns a Boolean indicating
    whether the resource should be evaluated on the provider. The evaluation is based on the rules defined in
    the resource's `included_children`, `excluded_children`, `included_parents`, and `excluded_parents`
    attributes, as well as the `iambic_managed` attribute of the resource and the provider details.

    Args:
    - resource: The resource to be evaluated.
    - provider_details: The provider details to use for the evaluation.
    - context (ExecutionContext): The execution context for the evaluation.
    - exclude_import_only (bool, optional): A flag indicating whether to exclude resources that are marked as
        import-only. Default is True.

    Returns:
    - A Boolean indicating whether the resource should be evaluated on the provider.
    """
    from iambic.core.models import AccessModelMixin

    no_op_values = [IambicManaged.DISABLED]
    if exclude_import_only:
        no_op_values.append(IambicManaged.IMPORT_ONLY)

    if (
        provider_details.iambic_managed in no_op_values
        or getattr(resource, "iambic_managed", None) in no_op_values
    ):
        return False

    if not isinstance(resource, AccessModelMixin):
        return True

    if provider_details.parent_id:
        if provider_details.parent_id in resource.excluded_parents:
            return False
        elif "*" not in resource.included_parents and not any(
            re.match(parent_id, provider_details.parent_id)
            for parent_id in resource.included_parents
        ):
            return False

    if not resource.included_children:
        return True

    provider_ids = sorted(provider_details.all_identifiers, key=len, reverse=True)
    included_children = sorted(
        [rule.lower() for rule in resource.included_children], key=len, reverse=True
    )
    excluded_children = sorted(
        [rule.lower() for rule in resource.excluded_children], key=len, reverse=True
    )
    exclude_weight = 0

    for exclude_rule in excluded_children:
        if exclude_rule == "*" or any(
            is_regex_match(exclude_rule, provider_id) for provider_id in provider_ids
        ):
            exclude_weight = len(exclude_rule)
            break

    for include_rule in included_children:
        if include_rule == "*" or any(
            is_regex_match(include_rule, provider_id) for provider_id in provider_ids
        ):
            return bool(len(include_rule) > exclude_weight)

    return False


def apply_to_provider(resource, provider_details, context: ExecutionContext) -> bool:
    if hasattr(resource, "deleted") and resource.deleted:
        return False

    return evaluate_on_provider(resource, provider_details, context)


def is_regex_match(regex, test_string):
    if "*" in regex:
        try:
            return re.match(regex.lower(), test_string)
        except re.error:
            return regex.lower() == test_string.lower()
    else:
        # it is not an actual regex string, just string comparison
        return regex.lower() == test_string.lower()


def get_provider_value(matching_values: list, identifiers: set[str]):
    """
    Get the provider value that matches the given identifiers.

    This function takes a list of matching values and a set of identifiers, and returns the matching value that
    has the highest priority for the given identifiers. The priority of the matching values is determined based
    on the rules defined in the `included_children` and `excluded_children` attributes of each matching value.

    Args:
    - matching_values (list): A list of matching values to search through.
    - identifiers (set[str]): A set of identifiers to match against the rules.

    Returns:
    - The matching value that has the highest priority for the given identifiers.
    """
    included_account_map = dict()
    included_account_lists = list()

    for matching_val in matching_values:
        for included_account in matching_val.included_children:
            included_account_map[included_account] = matching_val
            included_account_lists.append(included_account)

    for included_account in sorted(included_account_lists, key=len, reverse=True):
        cur_val = included_account_map[included_account]
        included_children = sorted(
            [rule.lower() for rule in cur_val.included_children], key=len, reverse=True
        )
        excluded_children = sorted(
            [rule.lower() for rule in cur_val.excluded_children], key=len, reverse=True
        )
        exclude_weight = 0

        for exclude_rule in excluded_children:
            if exclude_rule == "*" or any(
                is_regex_match(exclude_rule, provider_id) for provider_id in identifiers
            ):
                exclude_weight = len(exclude_rule)
                break

        for include_rule in included_children:
            if include_rule == "*" or any(
                is_regex_match(include_rule, provider_id) for provider_id in identifiers
            ):
                if len(include_rule) > exclude_weight:
                    return cur_val
                else:
                    break


class GlobalRetryController:
    """
    A context manager class that automatically retries a function in case of rate limit exceptions.

    This class provides a convenient way to wrap a function execution with rate limit handling. It retries the function
    in case of rate limit exceptions and stores the state of the rate limit in a global storage to ensure that all
    similarly executed functions are paused when a rate limit exception is encountered.

    Attributes:
        wait_time (int): The time to wait before retrying the function in case of rate limit exceptions (default is 60
                        seconds).
        retry_exceptions (list): A list of exceptions that will trigger a retry (default is
                                      [TimeoutError, asyncio.exceptions.TimeoutError, RateLimitException]).
        fn_identifier (str): An identifier for the function that is being executed, used to store the state of the rate
                             limit in the global storage (default is None, in which case the function name is used).
        max_retries (int): The maximum number of times to retry the function in case of rate limit exceptions
                           (default is 10).
    """

    def __init__(
        self,
        wait_time: int = 60,
        retry_exceptions: Optional[list[Any]] = None,
        fn_identifier: Optional[str] = None,
        max_retries: int = 10,
    ):
        if retry_exceptions is None:
            retry_exceptions = [
                TimeoutError,
                asyncio.exceptions.TimeoutError,
                RateLimitException,
            ]
        self.wait_time = wait_time
        self.retry_exceptions = retry_exceptions
        self.fn_identifier = fn_identifier
        self.max_retries = max_retries

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def __call__(self, func: typing.Callable, *args, **kwargs):
        if self.fn_identifier is not None:
            endpoint = self.fn_identifier
        else:
            endpoint = func.__name__
        retries = 0
        while retries < self.max_retries:
            try:
                res = await func(*args, **kwargs)
                if retries > 0:
                    log.info(f"Retry successful for {endpoint}.")
                return res
            except Exception as e:
                if type(e) not in self.retry_exceptions:
                    raise e
                if self.max_retries == retries + 1:
                    raise e
                if endpoint in RATE_LIMIT_STORAGE:
                    wait_time = (
                        RATE_LIMIT_STORAGE[endpoint] - asyncio.get_running_loop().time()
                    )
                    if wait_time > 0:
                        await asyncio.sleep(wait_time)
                    else:
                        del RATE_LIMIT_STORAGE[endpoint]
                RATE_LIMIT_STORAGE[endpoint] = (
                    asyncio.get_running_loop().time() + self.wait_time
                )
                retries += 1
                log.warning(
                    f"Rate limit hit for {endpoint}. Retrying in {self.wait_time} seconds."
                )


def sanitize_string(unsanitized_str, valid_characters_re):
    """
    This function sanitizes the session name typically passed as a parameter name, to ensure it is valid.
    """

    sanitized_str = ""
    max_length = 64  # Session names have a length limit of 64 characters
    for char in unsanitized_str:
        if len(sanitized_str) == max_length:
            break
        if re.match(valid_characters_re, char):
            sanitized_str += char
    return sanitized_str
