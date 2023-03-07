from __future__ import annotations

import asyncio
import datetime
import functools
import json
import os
import os.path
import sys
from enum import Enum
from typing import Any, Dict, List, Optional

import boto3
from pydantic import BaseModel as PydanticBaseModel

SHARED_FILESYSTEM_PREFIX = ""


class Command(Enum):
    IMPORT = "import"
    APPLY = "apply"
    CONFIG_DISCOVERY = "config_discovery"


class FakeExecutionMessage(PydanticBaseModel):
    execution_id: str
    command: Command
    provider_type: Optional[str]
    provider_id: Optional[str]
    metadata: Optional[Dict[str, Any]] = None
    templates: Optional[List[str]] = None
    requested_at: datetime.datetime = datetime.datetime.now(datetime.timezone.utc)


def lambda_handler(event, context):

    # path = "/mnt/efs/hello_world.txt"
    # lines = []
    # if os.path.exists(path):
    #     with open(path, "r") as f:
    #         lines = f.readlines()

    # print(lines)

    # lines.append("{0}\n".format(datetime.datetime.now()))

    # with open(path, "w") as f:
    #     f.writelines(lines)

    init_shared_filesystem_prefix("/mnt/efs")

    if "launch" in event:
        execution_id = datetime.datetime.now().isoformat()
        distribute_executions(execution_id)

    try:
        event_as_execution_message = FakeExecutionMessage(**event)
        execute_task(event_as_execution_message)
    except Exception:
        print("not an execution_message")

    return {"statusCode": 200, "body": json.dumps("Hello from Lambda!")}


def init_shared_filesystem_prefix(prefix: str):
    this_module = sys.modules[__name__]
    setattr(
        this_module,
        "SHARED_FILESYSTEM_PREFIX",
        prefix,
    )


# TODO fix invocation role (use IambicHubRoleSession or something)
async def run_task_on_lambda(execution_messages: list[FakeExecutionMessage]):
    loop = asyncio.get_running_loop()
    print("got {0} msgs".format(len(execution_messages)))
    lambda_client = boto3.client("lambda")
    function_name = os.environ.get("AWS_LAMBDA_FUNCTION_NAME")

    # resp = lambda_client.invoke(FunctionName=function_name, Payload=execution_messages[0].json())
    # print(resp)

    tasks = [
        loop.run_in_executor(
            None,
            functools.partial(
                lambda_client.invoke,
                FunctionName=function_name,
                Payload=execution_message.json(),
            ),
        )
        for execution_message in execution_messages
    ]
    print("got {0} tasks".format(len(tasks)))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        print(result)

    try:
        for execution_message in execution_messages:
            dir = f"/mnt/efs/{execution_message.execution_id}/"
            path = f"{dir}/task_{execution_message.metadata['task_id']}.txt"
            with open(path, "r") as f:
                lines = f.readlines()
                print(lines)
    except Exception:
        raise


def execute_task(execution_message: FakeExecutionMessage):
    dir = f"/mnt/efs/{execution_message.execution_id}/"
    os.makedirs(dir, exist_ok=True)
    path = f"{dir}/task_{execution_message.metadata['task_id']}.txt"
    with open(path, "w") as f:
        f.writelines([f"task_{execution_message.metadata['task_id']}"])


def distribute_executions(execution_id: str):

    execution_messages = [
        FakeExecutionMessage(
            execution_id=execution_id,
            command="import",
            metadata={"task_id": i},
        )
        for i in range(5)
    ]

    asyncio.run(run_task_on_lambda(execution_messages))
