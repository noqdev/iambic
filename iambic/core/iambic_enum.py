from __future__ import annotations

from enum import Enum


class IambicManaged(Enum):
    UNDEFINED = "undefined"
    READ_WRITE = "read_write"
    IMPORT_ONLY = "import_only"
