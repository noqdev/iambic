from __future__ import annotations

import datetime
import os.path
import tempfile

from iambic.plugins.v0_1_0.aws_lambda_remote_execution_engine.lambda_handler import (
    FakeExecutionMessage,
    execute_task,
    init_shared_filesystem_prefix,
)


def test_execute_tasks():
    temp_task_directory = tempfile.mkdtemp(prefix="iambic_test_tasks")
    init_shared_filesystem_prefix(temp_task_directory)
    execution_id = datetime.datetime.now().isoformat()
    execution_message = FakeExecutionMessage(
        execution_id=execution_id, command="import", metadata={"task_id": 0}
    )
    path = f"{temp_task_directory}/{execution_id}/task_0.txt"
    os.path.exists(path)


def test_run_task_on_lambda():
    pass
