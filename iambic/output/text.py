from __future__ import annotations

from typing import List

import rich

from iambic.core.models import TemplateChangeDetails
from iambic.output import get_template_env
from iambic.output.models import get_template_data


def file_render_resource_changes(
    filepath: str,
    resource_changes: List[TemplateChangeDetails],
) -> str:
    # Get template data
    template_data = get_template_data(resource_changes)
    # Get template environment
    env = get_template_env()
    # Render template
    template = env.get_template("text_file_summary.jinja2")
    rendered_data = template.render(iambic=template_data)
    with open(filepath, "w") as f:
        f.write(rendered_data)


def screen_render_resource_changes(resource_changes: List[TemplateChangeDetails]):
    template_data = get_template_data(resource_changes)
    env = get_template_env()
    template = env.get_template("text_screen_summary.jinja2")
    rendered_template = template.render(iambic=template_data)
    rich.print(rendered_template)
    return rendered_template
