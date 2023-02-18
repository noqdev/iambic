from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from unittest.mock import AsyncMock, patch

import git
import pytest
from pydantic import BaseModel

from iambic.config.dynamic_config import load_config
from iambic.core import git as the_git_module
from iambic.core.context import ExecutionContext
from iambic.core.iambic_plugin import ProviderPlugin
from iambic.core.models import BaseTemplate, ExpiryModel, TemplateChangeDetails
from iambic.plugins.v0_1_0 import PLUGIN_VERSION
from iambic.request_handler.git_apply import apply_git_changes

TEST_TEMPLATE_YAML = """template_type: NOQ::Test
name: test_template
expires_at: tomorrow
properties:
  name: {name}"""

TEST_TEMPLATE_TYPE = "NOQ::Test"
TEST_TEMPLATE_DIR = "resources/test/"
TEST_TEMPLATE_PATH = "resources/test/test_template.yaml"
TEST_CONFIG_DIR = "config/"
TEST_CONFIG_PATH = "config/test_config.yaml"

TEST_CONFIG_YAML = """template_type: NOQ::Core::Config
version: '1'

test:
    random: 1
"""


class TestConfig(BaseModel):
    test: str = "test"


class TestTemplateProperties(BaseModel):
    name: str


class TestTemplate(BaseTemplate, ExpiryModel):
    template_type = TEST_TEMPLATE_TYPE
    properties: TestTemplateProperties

    @property
    def resource_type(self):
        return "noq:test"

    @property
    def resource_id(self):
        return "fake_id"

    async def apply(
        self, config: TestConfig, context: ExecutionContext
    ) -> TemplateChangeDetails:
        template_changes = TemplateChangeDetails(
            resource_id="fake_id",
            resource_type="noq:test",
            template_path=self.file_path,
        )
        template_changes.proposed_changes = []
        return template_changes


def import_test_resources():
    pass


def load_test():
    pass


TEST_IAMBIC_PLUGIN = ProviderPlugin(
    config_name="aws",  # FIXME i can't seem to patch config to an different config object
    version=PLUGIN_VERSION,
    provider_config=TestConfig,
    requires_secret=True,
    async_import_callable=import_test_resources,
    async_load_callable=load_test,
    templates=[
        TestTemplate,
    ],
)


@pytest.fixture
def template_class():
    original_templates = the_git_module.TEMPLATES.templates
    the_git_module.TEMPLATES.set_templates(original_templates + [TestTemplate])
    with patch("iambic.core.git.TEMPLATES", the_git_module.TEMPLATES):
        yield the_git_module.TEMPLATES.template_map
    the_git_module.TEMPLATES.set_templates(original_templates)


@pytest.fixture
def templates_repo(template_class):

    temp_templates_directory = tempfile.mkdtemp(
        prefix="iambic_test_temp_templates_directory"
    )

    bare_directory = tempfile.mkdtemp(
        prefix="iambic_test_temp_templates_directory_bare"
    )

    try:
        bare_repo = git.Repo.init(f"{bare_directory}", bare=True)
        repo = bare_repo.clone(temp_templates_directory)
        repo_config_writer = repo.config_writer()
        repo_config_writer.set_value(
            "user", "name", "Iambic Github Functional Test for Github"
        )
        repo_config_writer.set_value(
            "user", "email", "github-cicd-functional-test@iambic.org"
        )
        repo_config_writer.release()

        os.makedirs(f"{temp_templates_directory}/{TEST_TEMPLATE_DIR}")
        os.makedirs(f"{temp_templates_directory}/{TEST_CONFIG_DIR}")

        with open(f"{temp_templates_directory}/{TEST_TEMPLATE_PATH}", "w") as f:
            f.write(TEST_TEMPLATE_YAML.format(name="before"))

        with open(f"{temp_templates_directory}/{TEST_CONFIG_PATH}", "w") as f:
            f.write(TEST_CONFIG_YAML)

        repo.git.add(A=True)
        repo.git.commit(m="before")
        repo.remotes.origin.push()

        with open(f"{temp_templates_directory}/{TEST_TEMPLATE_PATH}", "w") as f:
            f.write(TEST_TEMPLATE_YAML.format(name="after"))

        repo.git.add(A=True)
        repo.git.commit(m="after")

        config = asyncio.run(
            load_config(f"{temp_templates_directory}/{TEST_CONFIG_PATH}")
        )
        config.plugin_instances = [TEST_IAMBIC_PLUGIN]
        setattr(config, TEST_IAMBIC_PLUGIN.config_name, config)
        the_git_module.TEMPLATES.set_templates([TestTemplate])
        async_mock = AsyncMock(return_value=config)
        with patch(
            "iambic.request_handler.git_apply.load_config", side_effect=async_mock
        ):
            yield f"{temp_templates_directory}/{TEST_CONFIG_PATH}", temp_templates_directory
    finally:
        try:
            shutil.rmtree(temp_templates_directory)
            shutil.rmtree(bare_directory)
        except Exception as e:
            print(e)


@pytest.mark.asyncio
async def test_apply_git_changes(templates_repo):
    config_path, repo_dir = templates_repo
    with open(f"{repo_dir}/{TEST_TEMPLATE_PATH}", "r") as f:
        before_template_content = "\n".join(f.readlines())
    assert "tomorrow" in before_template_content
    await apply_git_changes(config_path, repo_dir)
    with open(f"{repo_dir}/{TEST_TEMPLATE_PATH}", "r") as f:
        after_template_content = "\n".join(f.readlines())
    assert "tomorrow" not in after_template_content
