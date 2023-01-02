from __future__ import annotations

import os

from iambic.okta.app.models import get_app_template
from iambic.okta.app.utils import list_all_apps


async def generate_app_templates(config, output_dir, okta_organization):
    """List all apps in the domain, along with members and
    settings"""

    apps = await list_all_apps(okta_organization)

    base_path = os.path.expanduser(output_dir)
    for okta_app in apps:
        app = await get_app_template(okta_app)
        file_path = os.path.expanduser(app.file_path)
        app.file_path = os.path.join(base_path, file_path)
        app.write()
    return apps
