from __future__ import annotations

IAMBIC_APPLY_ERROR_METADATA = "<!--iambic/apply/error-->"


def is_iambic_apply_error(body: str):
    footer = body.split("\n")[-1]
    return IAMBIC_APPLY_ERROR_METADATA in footer
