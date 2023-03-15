from __future__ import annotations

from typing import Any, Dict

import pytest
from iambic.plugins.v0_1_0.aws.iam.user.utils import list_users


class FakeIamClient(object):
    def get_account_authorization_details(self, *args, **kwargs) -> Dict[str, Any]:
        return {
            "UserDetailList": [
                {
                    "UserName": "test_user",
                    "PermissionsBoundary": {
                        "PermissionsBoundaryType": "PermissionsBoundaryPolicy",
                        "PermissionsBoundaryArn": "string",
                    },
                }
            ],
            "IsTruncated": False,
        }

    def list_users(self, *args, **kwargs) -> Dict[str, Any]:
        return {
            "Users": [
                {
                    "RoleName": "test_user",
                }
            ],
            "IsTruncated": False,
        }


@pytest.fixture
def iam_client():
    # until we can integration moto library, we are faking some iam methods
    return FakeIamClient()


@pytest.mark.asyncio
async def test_list_users(iam_client):
    roles = await list_users(iam_client)
    assert len(roles) > 0
