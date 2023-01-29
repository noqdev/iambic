from __future__ import annotations

from typing import List

import pytest

from iambic.core.models import BaseModel
from iambic.core.utils import create_commented_map, sort_dict, transform_commments, yaml


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
