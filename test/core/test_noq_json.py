from decimal import Decimal
from uuid import UUID
from datetime import datetime
from deepdiff.model import PrettyOrderedSet
from iambic.core.noq_json import dumps, loads


def test_set_encoder():
    data = {
        "a_set": {1, 2, 3},
        "a_frozenset": frozenset([4, 5, 6]),
        "a_pretty_ordered_set": PrettyOrderedSet({"a", "b"}),
        "a_decimal": Decimal("3.14159"),
        "a_datetime": datetime(2023, 4, 10, 12, 34, 56),
        "an_exception": ValueError("Test exception"),
        "a_uuid": UUID("12345678-1234-5678-1234-567812345678"),
        "a_list": [1, 2, 3],
    }

    encoded_data = dumps(data)
    decoded_data = loads(encoded_data)

    assert decoded_data == {
        "a_set": [1, 2, 3],
        "a_frozenset": [4, 5, 6],
        "a_pretty_ordered_set": ["a", "b"],
        "a_decimal": 3.14159,
        "a_datetime": "2023-04-10 12:34:56 ",
        "an_exception": "Test exception",
        "a_uuid": "12345678-1234-5678-1234-567812345678",
        "a_list": [1, 2, 3],
    }


def test_dumps_ujson():
    data = {
        "key": "value",
    }
    result = dumps(data)
    assert result == '{\n"key": "value"\n}'


def test_dumps_fallback():
    data = {
        "a_set": {1, 2, 3},
    }
    result = dumps(data)
    assert result == '{\n"a_set": [\n1,\n2,\n3\n]\n}'


def test_loads_ujson():
    data = '{"key":"value"}'
    result = loads(data)
    assert result == {"key": "value"}


def test_loads_fallback():
    data = '{"a_set":[1,2,3]}'
    result = loads(data)
    assert result == {"a_set": [1, 2, 3]}