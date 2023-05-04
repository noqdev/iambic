from __future__ import annotations

import asyncio

import pytest

from iambic.plugins.v0_1_0.aws.handlers import import_organization_resources


class TestImportOrganizationResource:
    @pytest.mark.asyncio
    async def test_import_organization_resources(
        self,
        mock_execution_message,
        mock_aws_config,
        mock_fs,
        mock_organizations_client,
    ):
        _ = mock_organizations_client
        config = mock_aws_config()
        _, templates_base_dir = mock_fs

        tasks = await import_organization_resources(
            mock_execution_message(), config, templates_base_dir, [], remote_worker=None
        )

        tasks = await asyncio.gather(*tasks)

        assert tasks
