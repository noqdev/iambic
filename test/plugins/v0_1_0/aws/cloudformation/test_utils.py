from __future__ import annotations

import boto3
import pytest
from aws_error_utils.aws_error_utils import make_aws_error
from botocore.exceptions import ClientError
from moto import mock_cloudformation

from iambic.plugins.v0_1_0.aws.cloud_formation.utils import create_stack_set, log


@pytest.fixture
def mock_cloudformation_client():
    with mock_cloudformation():
        yield


@pytest.mark.asyncio
async def test_create_stack_set_raise_exception(mock_cloudformation_client, mocker):
    client = boto3.client("cloudformation")
    mock = mocker.patch(
        "iambic.plugins.v0_1_0.aws.cloud_formation.utils.boto_crud_call"
    )

    def _mock_function():
        global acc
        acc = 0

        def _(*args, **kwargs):
            global acc
            acc = acc + 1  # noqa: F823
            if acc == 1:
                raise client.exceptions.StackSetNotFoundException({}, "")
            else:
                raise make_aws_error(
                    "ClientError",
                    "You must enable organizations access to operate a service managed stack set",
                    "",
                )

        return _

    mock.side_effect = _mock_function()
    error = mocker.spy(log, "error")

    with pytest.raises(ClientError):
        await create_stack_set(
            client,
            stack_set_name="stack",
            template_body="str",
            parameters=[],
            deployment_targets={},
            deployment_regions=[],
            operation_preferences={},
        )
        error.assert_called_once()
