from __future__ import annotations

import pytest

from iambic.core.models import TemplateChangeDetails
from iambic.output.text import screen_render_resource_changes

from . import get_templates_mixed


@pytest.mark.parametrize(
    "template_change_details, expected_outputs",
    [
        (
            get_templates_mixed(),
            [
                "aws:iam:role // product-dev_iambic_test_role",
                "design-prod - (006933239187)",
                "Iambic Standalone Org - (566255053759)",
                "aws:iam:role // design-dev_iambic_test_role",
                "aws:iam:role // design-workspaces_iambic_test_role",
                "design-prod - (006933239187)",
            ]
        ),
    ],
)
def test_screen_render_resource_changes(
    template_change_details: list[TemplateChangeDetails],
    expected_outputs: str,
):
    rendered_text = screen_render_resource_changes(template_change_details)
    output = rendered_text
    for expected_output in expected_outputs:
        assert expected_output in output
