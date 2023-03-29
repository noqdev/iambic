from __future__ import annotations

import pytest
from rich import print

from iambic.core.models import TemplateChangeDetails
from iambic.output.text import file_render_resource_changes, screen_render_resource_changes

from . import get_update_template, get_templates_mixed


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
        (
            get_update_template(),
            [
                "resources/aws/roles/demo-1/t1000.yaml",
            ]

        )
    ],
)
def test_screen_render_resource_changes(
    template_change_details: list[TemplateChangeDetails],
    expected_outputs: str,
):
    rendered_text = screen_render_resource_changes(template_change_details)
    output = rendered_text
    print(output)
    for expected_output in expected_outputs:
        assert expected_output in output


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
        (
            get_update_template(),
            [
                "resources/aws/roles/demo-1/t1000.yaml",
            ]

        )
    ],
)
def test_file_render_resource_changes(
    tmp_path,
    template_change_details: list[TemplateChangeDetails],
    expected_outputs: str,
):
    test_file = tmp_path / "test_file_render_resource_changes.txt"
    file_render_resource_changes(str(test_file), template_change_details)
    
    with open(test_file, "r") as f:
        output = f.read()
    for expected_output in expected_outputs:
        assert expected_output in output
