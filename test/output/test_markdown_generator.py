from __future__ import annotations

import pytest

from iambic.core.models import TemplateChangeDetails
from iambic.output.markdown import gh_render_resource_changes
from iambic.output.models import ActionSummaries, get_template_data

from . import get_templates_mixed, get_update_template


@pytest.mark.parametrize(
    "template_change_details, expected_output",
    [
        (
            get_templates_mixed(),
            ActionSummaries(num_accounts=10, num_actions=1, num_templates=2),
        ),
        (
            get_update_template(),
            ActionSummaries(num_accounts=1, num_actions=1, num_templates=1),
        ),
    ],
)
def test_get_template_data(
    template_change_details: list[TemplateChangeDetails],
    expected_output: ActionSummaries,
):
    template_data = get_template_data(template_change_details)
    assert template_data.num_accounts == expected_output.num_accounts
    assert template_data.num_actions == expected_output.num_actions
    assert template_data.num_templates == expected_output.num_templates


@pytest.mark.parametrize(
    "template_change_details, expected_output",
    [
        (
            get_templates_mixed(),
            ActionSummaries(num_accounts=10, num_actions=1, num_templates=2),
        ),
        (
            get_update_template(),
            ActionSummaries(num_accounts=10, num_actions=1, num_templates=1),
        ),
    ],
)
def test_gh_render_resource_changes(
    template_change_details: list[TemplateChangeDetails],
    expected_output: ActionSummaries,
):
    rendered_markdown = gh_render_resource_changes(template_change_details)
    assert rendered_markdown != ""
