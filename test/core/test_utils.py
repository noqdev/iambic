from __future__ import annotations

import asyncio
import unittest
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from iambic.core.models import BaseModel
from iambic.core.utils import (
    GlobalRetryController,
    create_commented_map,
    sort_dict,
    transform_commments,
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


class ForrestModel(BaseModel):

    forrest: List[TreeModel]


TEST_COMMENTED_YAML = """forrest:  # forrest-comment
    - name: simple_tree # COMMENT
"""


def test_commmented_yaml():
    yaml_dict = yaml.load(TEST_COMMENTED_YAML)
    yaml_dict = transform_commments(yaml_dict)
    commented_model = ForrestModel(**yaml_dict)
    commented_map = create_commented_map(commented_model.dict())
    as_yaml = yaml.dump(commented_map)
    assert "COMMENT" in as_yaml


class TestGlobalRetryController(unittest.TestCase):
    def setUp(self):
        self.wait_time = 1
        self.rate_limit_exceptions = [TimeoutError, asyncio.exceptions.TimeoutError]
        self.fn_identifier = None
        self.max_retries = 10
        self.retry_controller = GlobalRetryController(
            wait_time=self.wait_time,
            rate_limit_exceptions=self.rate_limit_exceptions,
            fn_identifier=self.fn_identifier,
            max_retries=self.max_retries,
        )

    @patch("iambic.core.utils.RATE_LIMIT_STORAGE")
    @patch("asyncio.sleep")
    async def test_retry_controller_retries_on_timeout_error(
        self, mock_sleep, mock_rate_limit_storage
    ):
        mock_func = MagicMock(side_effect=TimeoutError)
        mock_rate_limit_storage.get.return_value = None
        with self.assertRaises(TimeoutError):
            await self.retry_controller(mock_func)
        self.assertEqual(mock_func.call_count, self.max_retries)
        self.assertEqual(mock_sleep.call_count, self.max_retries - 1)

    @patch("iambic.core.utils.RATE_LIMIT_STORAGE")
    @patch("asyncio.sleep")
    async def test_retry_controller_retries_on_asyncio_timeout_error(
        self, mock_sleep, mock_rate_limit_storage
    ):
        mock_func = MagicMock(side_effect=asyncio.exceptions.TimeoutError)
        mock_rate_limit_storage.get.return_value = None
        with self.assertRaises(asyncio.exceptions.TimeoutError):
            await self.retry_controller(mock_func)
        self.assertEqual(mock_func.call_count, self.max_retries)
        self.assertEqual(mock_sleep.call_count, self.max_retries - 1)

    @patch("iambic.core.utils.RATE_LIMIT_STORAGE")
    async def test_retry_controller_does_not_retry_on_other_errors(
        self, mock_rate_limit_storage
    ):
        mock_func = MagicMock(side_effect=Exception)
        mock_rate_limit_storage.get.return_value = None
        with self.assertRaises(Exception):
            await self.retry_controller(mock_func)
        self.assertEqual(mock_func.call_count, 1)

    @patch("iambic.core.utils.RATE_LIMIT_STORAGE")
    async def test_retry_controller_returns_result_on_success(
        self, mock_rate_limit_storage
    ):
        mock_func = MagicMock(return_value="success")
        mock_rate_limit_storage.get.return_value = None
        result = await self.retry_controller(mock_func)
        self.assertEqual(result, "success")
        self.assertEqual(mock_func.call_count, 1)

    @patch("iambic.core.utils.RATE_LIMIT_STORAGE")
    async def test_retry_controller_retries_up_to_max_retries(
        self, mock_rate_limit_storage
    ):
        mock_func = MagicMock(side_effect=TimeoutError)
        mock_rate_limit_storage.get.return_value = None
        with self.assertRaises(TimeoutError):
            await self.retry_controller(mock_func)
        self.assertEqual(mock_func.call_count, self.max_retries)

    @patch("iambic.core.utils.RATE_LIMIT_STORAGE")
    async def test_retry_controller_uses_custom_identifier(
        self, mock_rate_limit_storage
    ):
        self.fn_identifier = "custom_endpoint"
        self.retry_controller = GlobalRetryController(
            wait_time=self.wait_time,
            rate_limit_exceptions=self.rate_limit_exceptions,
            fn_identifier=self.fn_identifier,
            max_retries=self.max_retries,
        )
        mock_func = MagicMock(side_effect=TimeoutError)
        mock_rate_limit_storage.get.return_value = None
        with self.assertRaises(TimeoutError):
            await self.retry_controller(mock_func)
        mock_rate_limit_storage.__setitem__.assert_called_with(
            self.fn_identifier,
            mock_rate_limit_storage.__getitem__.return_value + self.wait_time,
        )
