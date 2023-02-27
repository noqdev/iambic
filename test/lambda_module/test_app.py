from __future__ import annotations

import os
import tempfile

import pytest

iambic_module = __import__("iambic.lambda.app", globals(), locals(), [], 0)


def test_init_repo_base_path_outside_of_lambda():
    old_repo_base_path = getattr(iambic_module, "lambda").app.REPO_BASE_PATH
    assert not old_repo_base_path.startswith(tempfile.gettempdir())
    assert os.environ.get("AWS_LAMBDA_FUNCTION_NAME", False) is False
    getattr(iambic_module, "lambda").app.init_repo_base_path()
    new_repo_base_path = getattr(iambic_module, "lambda").app.REPO_BASE_PATH
    assert os.path.exists(new_repo_base_path)


@pytest.fixture
def mock_aws_lambda_function_name():
    old_value = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", None)
    os.environ["AWS_LAMBDA_FUNCTION_NAME"] = "fake_function_name"
    yield os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
    if old_value is None:
        del os.environ["AWS_LAMBDA_FUNCTION_NAME"]
    else:
        os.environ["AWS_LAMBDA_FUNCTION_NAME"] = old_value


def test_init_repo_base_path_inside_of_lambda(mock_aws_lambda_function_name):
    old_repo_base_path = getattr(iambic_module, "lambda").app.REPO_BASE_PATH
    assert not old_repo_base_path.startswith(tempfile.gettempdir())
    assert os.environ.get("AWS_LAMBDA_FUNCTION_NAME", False)
    getattr(iambic_module, "lambda").app.init_repo_base_path()
    new_repo_base_path = getattr(iambic_module, "lambda").app.REPO_BASE_PATH
    assert new_repo_base_path.startswith(tempfile.gettempdir())
    assert old_repo_base_path != new_repo_base_path
    assert os.path.exists(new_repo_base_path)
