from __future__ import annotations

import pytest

from iambic.core.models import TemplateChangeDetails
from iambic.output.text import screen_render_resource_changes
from iambic.output.models import ActionSummaries

from rich import print

from . import get_templates_mixed


@pytest.mark.parametrize(
    "template_change_details, expected_output",
    [
        (
            get_templates_mixed(),
            ActionSummaries(num_accounts=10, num_actions=1, num_templates=2),
        ),
    ],
)
def test_screen_render_resource_changes(
    template_change_details: list[TemplateChangeDetails],
    expected_output: ActionSummaries,
):
    rendered_text = screen_render_resource_changes(template_change_details)
    print(rendered_text)
