from __future__ import annotations

from typing import Generator
from unittest import mock
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def os_path() -> Generator[None, None, None]:
    """Mocks out the OS path to return an easy slashed string"""
    with mock.patch("os.path.join", side_effect=lambda *args: "/".join(args)):
        yield


@pytest.fixture
def mocked_repo() -> Generator[MagicMock, None, None]:
    """Mock out the iambic.core.git.Repo and return back the MagicMock"""
    with mock.patch("iambic.core.git.Repo", autospec=True) as mock_repo:
        yield mock_repo
