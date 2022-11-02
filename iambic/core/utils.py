import asyncio
import glob
import os
import pathlib
import re
from io import StringIO
from typing import Union

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
    if not replace_file and os.path.exists(file_path):
        async with aiofiles.open(file_path, mode="r") as f:
            content_dict = json.loads(await f.read())
            content_as_dict = {**content_dict, **content_as_dict}

    async with aiofiles.open(file_path, mode="w") as f:
        await f.write(json.dumps(content_as_dict, indent=2))


async def file_regex_search(file_path: str, re_pattern: str) -> Union[str , None]:
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
    file_paths = glob.glob(f"{repo_dir}/**/*.yaml", recursive=True)
    file_paths += glob.glob(f"{repo_dir}*.yaml", recursive=True)
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

    async def process(self, messages: list[dict]):
        return await asyncio.gather(
            *[asyncio.create_task(self.handle_message(**msg)) for msg in messages]
        )


typ = "rt"
yaml = NoqYaml(typ=typ)
yaml.preserve_quotes = True
yaml.indent(mapping=2, sequence=4, offset=2)
yaml.representer.ignore_aliases = lambda *data: True
yaml.width = 4096
