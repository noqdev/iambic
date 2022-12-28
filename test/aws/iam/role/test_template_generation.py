from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from iambic.aws.iam.role.models import RoleTemplate
from iambic.aws.iam.role.template_generation import create_templated_role
from iambic.aws.models import AWSAccount
from iambic.core.iambic_enum import IambicManaged


@pytest.fixture
def test_role():
    test_role_name = "test_role"
    test_role = RoleTemplate(
        identifier=test_role_name,
        included_accounts=["dev"],
        file_path="/tmp/test_role.yaml",
        properties={"role_name": test_role_name},
    )
    return test_role


@pytest.fixture
def mock_account_id_to_role_map(test_role):
    with patch(
        "iambic.aws.iam.role.template_generation._account_id_to_role_map"
    ) as _mock_account_id_to_role_map:
        async_mock = AsyncMock(return_value={"dev": test_role.properties.dict()})
        _mock_account_id_to_role_map.side_effect = async_mock
        yield _mock_account_id_to_role_map


@pytest.fixture
def mock_write():
    with patch("iambic.core.models.BaseTemplate.write") as _mock_write:
        yield _mock_write


@pytest.mark.asyncio
async def test_create_template_role(test_role, mock_account_id_to_role_map, mock_write):
    test_config = MagicMock()
    test_aws_account_map = {
        "dev": AWSAccount(
            account_id="123456789012", account_name="dev", assume_role_arn=""
        )
    }
    test_role_name = "test_role"
    test_role_dir = ""
    test_role_refs = [test_role]
    test_existing_template_map = {}
    output_role = await create_templated_role(
        test_config,
        test_aws_account_map,
        test_role_name,
        test_role_refs,
        test_role_dir,
        test_existing_template_map,
    )
    assert output_role.iambic_managed is IambicManaged.UNDEFINED

    test_existing_template_map = {test_role_name: "fake_file_path"}
    with patch(
        "iambic.aws.iam.role.template_generation.load_templates"
    ) as _mock_load_templates:
        _mock_load_templates.return_value = [test_role]
        test_role.iambic_managed = IambicManaged.READ_AND_WRITE
        output_role = await create_templated_role(
            test_config,
            test_aws_account_map,
            test_role_name,
            test_role_refs,
            test_role_dir,
            test_existing_template_map,
        )
        assert output_role.iambic_managed is IambicManaged.READ_AND_WRITE
