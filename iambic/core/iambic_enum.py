from enum import Enum
from ruamel.yaml import yaml_object, YAML

yaml = YAML()

@yaml_object(yaml)
class IambicManaged(Enum):
    UNDEFINED = "undefined"
    READ_AND_WRITE = "read_and_write"
    IMPORT_ONLY = "import_only"

    @classmethod
    def to_yaml(cls, representer, node):
        return representer.represent_scalar(
            u'!IambicManaged', f'{node._value_}'
        )

    @classmethod
    def from_yaml(cls, constructor, node):
        return cls(node.value)
