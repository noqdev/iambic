from __future__ import annotations

from typing import Any, Dict

import pytest
from iambic.plugins.v0_1_0.aws.iam.role.utils import list_roles


class FakeIamClient(object):
    def get_account_authorization_details(self, *args, **kwargs) -> Dict[str, Any]:
        return {
            "RoleDetailList": [
                {
                    "RoleName": "test_role",
                    "PermissionsBoundary": {
                        "PermissionsBoundaryType": "PermissionsBoundaryPolicy",
                        "PermissionsBoundaryArn": "string",
                    },
                }
            ],
            "IsTruncated": False,
        }

    def list_roles(self, *args, **kwargs) -> Dict[str, Any]:
        return {
            "Roles": [
                {
                    "RoleName": "test_role",
                }
            ],
            "IsTruncated": False,
        }


@pytest.fixture
def iam_client():
    # until we can integration moto library, we are faking some iam methods
    return FakeIamClient()


@pytest.mark.asyncio
async def test_list_roles(iam_client):
    roles = await list_roles(iam_client)
    assert len(roles) > 0
