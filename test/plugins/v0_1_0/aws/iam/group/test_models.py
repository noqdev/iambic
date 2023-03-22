from __future__ import annotations

from iambic.plugins.v0_1_0.aws.iam.group.models import GroupProperties


def test_user_path_validation():
    path = [
        {"included_accounts": ["account_1", "account_2"], "file_path": "/engineering"},
        {"included_accounts": ["account_3"], "file_path": "/finance"},
    ]
    properties_1 = GroupProperties(group_name="foo", path=path)
    path_1 = properties_1.path
    path_2 = list(reversed(properties_1.path))
    assert path_1 != path_2  # because we reverse the list
    properties_1.path = path_2
    assert (
        properties_1.path == path_2
    )  # double check the list is reversed because validation doesn't happen after creation
    properties_1.validate_model_afterward()
    assert properties_1.path == path_1
