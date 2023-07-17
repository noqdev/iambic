from __future__ import annotations

from collections import defaultdict
from typing import Optional, Type

from iambic.core.models import BaseTemplate, ProviderChild
from iambic.core.utils import evaluate_on_provider


def group_detect_messages(group_by: str, messages: list) -> dict:
    """Group messages by a key in the message dict.

    Args:
        group_by (str): The key to group by.
        messages (list): The messages to group.

    Returns:
        dict: The grouped messages.
    """
    grouped_messages = defaultdict(list)
    for message in messages:
        grouped_messages[getattr(message, group_by)].append(message)

    return grouped_messages


def generate_template_output(
    excluded_provider_ids: list[str],
    provider_child_map: dict[str, ProviderChild],
    template: Optional[Type[BaseTemplate]],
) -> dict[str, dict]:
    provider_children_value_map = dict()
    if not template:
        return provider_children_value_map
    for provider_child_id, provider_child in provider_child_map.items():
        if provider_child_id in excluded_provider_ids:
            continue
        elif not evaluate_on_provider(
            template, provider_child, exclude_import_only=False
        ):
            continue

        if provider_child_value := template.apply_resource_dict(provider_child):
            provider_children_value_map[provider_child_id] = provider_child_value

    return provider_children_value_map
