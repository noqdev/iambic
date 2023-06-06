from __future__ import annotations

import asyncio
import unittest
from datetime import date, datetime, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from stringcase import pascalcase, snakecase

from iambic.core.models import BaseModel
from iambic.core.utils import (
    GlobalRetryController,
    convert_between_json_and_yaml,
    create_commented_map,
    evaluate_on_provider,
    normalize_dict_keys,
    simplify_dt,
    sort_dict,
    transform_comments,
    yaml,
)


@pytest.mark.parametrize(
    "test_input,expected",
    [
        (
            {
                "access_rules": [
                    {
                        "users": ["bob@example.com"],
                        "included_accounts": [{"space in account name"}],
                        "included_orgs": ["xyz"],
                    },
                    {
                        "included_accounts": [{"global_account_name"}],
                        "included_orgs": ["xyz"],
                        "users": ["alice@example.com"],
                    },
                ]
            },
            {
                "access_rules": [
                    {
                        "included_accounts": [{"space in account name"}],
                        "included_orgs": ["xyz"],
                        "users": ["bob@example.com"],
                    },
                    {
                        "included_accounts": [{"global_account_name"}],
                        "included_orgs": ["xyz"],
                        "users": ["alice@example.com"],
                    },
                ]
            },
        )
    ],
)
def test_sort_dict_stability(test_input, expected):
    assert sort_dict(test_input) == expected


class TreeModel(BaseModel):
    name: str


class TreeContainer(BaseModel):
    tree: TreeModel


class ForrestModel(BaseModel):
    forrest: List[TreeModel]


TEST_COMMENTED_YAML = """forrest:  # forrest-comment
    - name: simple_tree # COMMENT
"""


# be careful with this test, as the check is format sensitive
def test_file_header_commented_yaml():
    MULTILINE_YAML = """# HEADER LINE 1
# HEADER LINE 2
name: simple_tree
"""
    yaml_dict = yaml.load(MULTILINE_YAML)
    yaml_dict = transform_comments(yaml_dict)
    commented_model = TreeModel(**yaml_dict)
    commented_map = create_commented_map(commented_model.dict())
    as_yaml = yaml.dump(commented_map)
    assert MULTILINE_YAML == as_yaml


# be careful with this test, as the check is format sensitive
def test_no_file_header_commented_yaml():
    MULTILINE_YAML = """name: simple_tree
"""
    yaml_dict = yaml.load(MULTILINE_YAML)
    yaml_dict = transform_comments(yaml_dict)
    commented_model = TreeModel(**yaml_dict)
    commented_map = create_commented_map(commented_model.dict())
    as_yaml = yaml.dump(commented_map)
    assert MULTILINE_YAML == as_yaml


def test_commented_yaml():
    yaml_dict = yaml.load(TEST_COMMENTED_YAML)
    yaml_dict = transform_comments(yaml_dict)
    commented_model = ForrestModel(**yaml_dict)
    commented_map = create_commented_map(commented_model.dict())
    as_yaml = yaml.dump(commented_map)
    assert "COMMENT" in as_yaml


# be careful with this test, as the check is format sensitive
def test_file_footer_commented_yaml():
    MULTILINE_YAML = """name: simple_tree  # LINE 1
# LINE 2
"""
    yaml_dict = yaml.load(MULTILINE_YAML)
    yaml_dict = transform_comments(yaml_dict)
    commented_model = TreeModel(**yaml_dict)
    commented_map = create_commented_map(commented_model.dict())
    as_yaml = yaml.dump(commented_map)
    assert MULTILINE_YAML == as_yaml


# be careful with this test, as the check is format sensitive
# this test case is commented out because raumel actually cannot write
# out such pre-value-comments.
# def test_after_key_pre_value_commented_yaml():
#     MULTILINE_YAML = """name:
#   # pre-value-comment
#   simple_tree  # LINE 1
# # LINE 2
# """
#     yaml_dict = yaml.load(MULTILINE_YAML)
#     yaml_dict = transform_comments(yaml_dict)
#     commented_model = TreeModel(**yaml_dict)
#     commented_map = create_commented_map(commented_model.dict())
#     as_yaml = yaml.dump(commented_map)
#     assert MULTILINE_YAML == as_yaml


# be careful with this test, as the check is format sensitive
def test_after_key_pre_key_commented_yaml():
    MULTILINE_YAML = """tree:
  # pre-key-comment
  name: simple_tree  # LINE 1
# LINE 2
"""
    yaml_dict = yaml.load(MULTILINE_YAML)
    yaml_dict = transform_comments(yaml_dict)
    commented_model = TreeContainer(**yaml_dict)
    commented_map = create_commented_map(commented_model.dict())
    as_yaml = yaml.dump(commented_map)
    assert MULTILINE_YAML == as_yaml


# be careful with this test, as the check is format sensitive
def test_after_value_newline_commented_yaml_2():
    MULTILINE_YAML = """tree:
  # pre-key-comment
  name: simple_tree
  # LINE 1
"""
    yaml_dict = yaml.load(MULTILINE_YAML)
    yaml_dict = transform_comments(yaml_dict)
    commented_model = TreeContainer(**yaml_dict)
    commented_map = create_commented_map(commented_model.dict())
    as_yaml = yaml.dump(commented_map)
    assert MULTILINE_YAML == as_yaml


def test_inner_comment():
    MULTILINE_YAML = """
  tree:
    name: simple_tree # COMMENT
    """
    yaml_dict = yaml.load(MULTILINE_YAML)
    yaml_dict = transform_comments(yaml_dict)
    commented_model = TreeContainer(**yaml_dict)
    commented_map = create_commented_map(commented_model.dict())
    as_yaml = yaml.dump(commented_map)
    assert "COMMENT" in as_yaml


def test_multiline_comment_yaml():
    MULTILINE_YAML = """
forrest:
  # comment line 1
  # comment line 2
  # comment line 3
  - name: simple_tree # COMMENT
    """
    yaml_dict = yaml.load(MULTILINE_YAML)
    yaml_dict = transform_comments(yaml_dict)
    commented_model = ForrestModel(**yaml_dict)
    commented_map = create_commented_map(commented_model.dict())
    as_yaml = yaml.dump(commented_map)
    assert "# comment line 1" in as_yaml


def test_commented_out_list_element_yaml():
    MULTILINE_YAML = """
forrest:
  - name: simple_tree # COMMENT
  # - name: commented_out_tree
    """
    yaml_dict = yaml.load(MULTILINE_YAML)
    yaml_dict = transform_comments(yaml_dict)
    commented_model = ForrestModel(**yaml_dict)
    commented_map = create_commented_map(commented_model.dict())
    as_yaml = yaml.dump(commented_map)
    assert "commented_out_tree" in as_yaml


class TestGlobalRetryController(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.wait_time = 1
        self.retry_exceptions = [TimeoutError, asyncio.exceptions.TimeoutError]
        self.fn_identifier = None
        self.max_retries = 10
        self.retry_controller = GlobalRetryController(
            wait_time=self.wait_time,
            retry_exceptions=self.retry_exceptions,
            fn_identifier=self.fn_identifier,
            max_retries=self.max_retries,
        )

    @patch.dict("iambic.core.utils.RATE_LIMIT_STORAGE")
    @patch("asyncio.sleep")
    async def test_retry_controller_retries_on_timeout_error(self, mock_sleep):
        mock_func = AsyncMock(__name__="AsyncMock", side_effect=TimeoutError)
        with self.assertRaises(TimeoutError):
            await self.retry_controller(mock_func)
        self.assertEqual(mock_func.call_count, self.max_retries)
        self.assertGreaterEqual(mock_sleep.call_count, self.max_retries - 2)

    @patch.dict("iambic.core.utils.RATE_LIMIT_STORAGE", {})
    @patch("asyncio.sleep")
    async def test_retry_controller_retries_on_asyncio_timeout_error(self, mock_sleep):
        # Every time `mock_func` is called, it will raise a TimeoutError,
        # which will be caught by the retry controller and retried 9 times.
        # On the 10th try the exception will be raised.
        mock_func = AsyncMock(
            __name__="AsyncMock", side_effect=asyncio.exceptions.TimeoutError
        )
        # mock_rate_limit_storage.get.return_value = None
        with self.assertRaises(asyncio.exceptions.TimeoutError):
            await self.retry_controller(mock_func)
        self.assertEqual(mock_func.call_count, self.max_retries)
        self.assertEqual(mock_sleep.call_count, self.max_retries - 2)

    @patch.dict("iambic.core.utils.RATE_LIMIT_STORAGE")
    @patch("asyncio.sleep")
    async def test_retry_controller_does_not_retry_on_other_errors(self, mock_sleep):
        mock_func = AsyncMock(__name__="AsyncMock", side_effect=Exception)
        with self.assertRaises(Exception):
            await self.retry_controller(mock_func)
        self.assertEqual(mock_func.call_count, 1)
        self.assertEqual(mock_sleep.call_count, 0)

    @patch.dict("iambic.core.utils.RATE_LIMIT_STORAGE")
    @patch("asyncio.sleep")
    async def test_retry_controller_returns_result_on_success(self, mock_sleep):
        mock_func = AsyncMock(__name__="AsyncMock", return_value="success")
        result = await self.retry_controller(mock_func)
        self.assertEqual(result, "success")
        self.assertEqual(mock_func.call_count, 1)
        self.assertEqual(mock_sleep.call_count, 0)

    @patch.dict("iambic.core.utils.RATE_LIMIT_STORAGE")
    @patch("asyncio.sleep")
    async def test_retry_controller_retries_up_to_max_retries(self, mock_sleep):
        mock_func = AsyncMock(__name__="AsyncMock", side_effect=TimeoutError)
        with self.assertRaises(TimeoutError):
            await self.retry_controller(mock_func)
        self.assertEqual(mock_func.call_count, self.max_retries)
        self.assertGreaterEqual(mock_sleep.call_count, self.max_retries - 2)

    @patch.dict("iambic.core.utils.RATE_LIMIT_STORAGE")
    @patch("asyncio.sleep")
    async def test_retry_controller_uses_custom_identifier(self, mock_sleep):
        self.fn_identifier = "custom_endpoint"
        self.retry_controller = GlobalRetryController(
            wait_time=self.wait_time,
            retry_exceptions=self.retry_exceptions,
            fn_identifier=self.fn_identifier,
            max_retries=self.max_retries,
        )
        mock_func = AsyncMock(__name__="AsyncMock", side_effect=TimeoutError)
        with self.assertRaises(TimeoutError):
            await self.retry_controller(mock_func)
        self.assertGreaterEqual(mock_sleep.call_count, self.max_retries - 2)


class TestSimplifyDt(unittest.TestCase):
    def test_utc_datetime(self):
        dt = datetime(2022, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        expected_result = "2022-12-31T23:59 UTC"
        self.assertEqual(simplify_dt(dt), expected_result)

    def test_naive_datetime(self):
        dt = datetime(2022, 12, 31, 23, 59, 59)
        expected_result = "2022-12-31T23:59 UTC"
        self.assertEqual(simplify_dt(dt), expected_result)

    def test_date(self):
        d = date(2022, 12, 31)
        expected_result = "2022-12-31T00:00 UTC"
        self.assertEqual(simplify_dt(d), expected_result)

    def test_none_datetime(self):
        self.assertIsNone(simplify_dt(None))

    def test_non_date_input(self):
        input_value = "not a date"
        expected_result = input_value
        self.assertEqual(simplify_dt(input_value), expected_result)


@pytest.mark.asyncio
async def test_gather_templates(tmpdir):
    from iambic.core.utils import Path, gather_templates

    # Create a test directory structure
    templates_dir = tmpdir.mkdir("templates")
    sub_dir1 = templates_dir.mkdir("sub_dir1")
    sub_dir2 = templates_dir.mkdir("sub_dir2")
    file1 = templates_dir.join("file1.yml")
    file1.write("template_type: NOQ::type1\n")
    file2 = sub_dir1.join("file2.yaml")
    file2.write("template_type: NOQ::type2\n")
    file3 = sub_dir2.join("file3.yml")
    file3.write("template_type: NOQ::type1\n")
    file4 = sub_dir2.join("file4.yaml")
    file4.write("template_type: not_noq\n")
    top_level_file = templates_dir.join("top_level.yaml")
    top_level_file.write("template_type:  NOQ::top_level\n")

    # Test the function
    result = await gather_templates(str(templates_dir), "type1")
    assert set(result) == {
        Path(file1),
        Path(file3),
    }

    result = await gather_templates(str(templates_dir), "type2")
    assert set(result) == {
        Path(file2),
    }

    result = await gather_templates(str(templates_dir), "type3")
    assert set(result) == set()

    result = await gather_templates(str(templates_dir))
    assert set(result) == {
        Path(file1),
        Path(file2),
        Path(file3),
        Path(top_level_file),
    }

    # Test the function when path is a directory with ending /
    assert not str(templates_dir).endswith("/")
    result = await gather_templates(str(templates_dir) + "/", "top_level")
    assert set(result) == {
        Path(top_level_file),
    }
    # despite the function signature returns a list, we expect all
    # elements to be unique.
    assert len(result) == len(set(result))

    # Test the function when path is a directory without ending /
    assert not str(templates_dir).endswith("/")
    result = await gather_templates(str(templates_dir), "top_level")
    assert set(result) == {
        Path(top_level_file),
    }
    # despite the function signature returns a list, we expect all
    # elements to be unique.
    assert len(result) == len(set(result))


def test_normalize_dict_keys():
    # Test converting dictionary keys to snake_case
    data = {"MyKey": {"InnerKey": "value"}}
    expected_result = {"my_key": {"inner_key": "value"}}
    result = normalize_dict_keys(data, snakecase)
    assert result == expected_result

    # Test converting dictionary keys to PascalCase
    data = {"my_key": {"inner_key": "value"}}
    expected_result = {"MyKey": {"InnerKey": "value"}}
    result = normalize_dict_keys(data, pascalcase)
    assert result == expected_result


def test_convert_between_json_and_yaml():
    # Test converting JSON to YAML
    json_input = '{"MyKey": {"InnerKey": "value"}}'
    yaml_output = convert_between_json_and_yaml(json_input)
    assert "my_key:\n  inner_key: value\n" in yaml_output

    # Test converting YAML to JSON
    yaml_input = "my_key:\n  inner_key: value\n"
    json_output = convert_between_json_and_yaml(yaml_input)
    expected_json_output = '{\n  "MyKey": {\n    "InnerKey": "value"\n  }\n}'
    assert json_output == expected_json_output


def test_evaluate_on_provider_organization_account():
    resource = MagicMock()
    provider_details = MagicMock()

    resource.organization_account_needed = True
    provider_details.organization_account = True

    assert evaluate_on_provider(resource, provider_details)
