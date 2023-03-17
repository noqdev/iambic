from __future__ import annotations

import pathlib
from typing import List

from jinja2 import Environment, FileSystemLoader

from iambic.core.models import (
    TemplateChangeDetails,
)
from iambic.output import get_template_env
from iambic.output.models import get_template_data


def file_render_resource_changes(resource_changes: List[TemplateChangeDetails]):
    template_data = get_template_data(resource_changes)
    env = get_template_env()
    template = env.get_template("text_file_summary.jinja2")
    return template.render(iambic=template_data)


def screen_render_resource_changes(resource_changes: List[TemplateChangeDetails]):
    template_data = get_template_data(resource_changes)
    env = get_template_env()
    template = env.get_template("text_screen_summary.jinja2")
    return template.render(iambic=template_data)
