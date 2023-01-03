from enum import Enum


class IambicManaged(Enum):
    UNDEFINED = "undefined"
    READ_AND_WRITE = "read_and_write"
    IMPORT_ONLY = "import_only"
