import pathlib
from jinja2 import Environment, FileSystemLoader


def get_template_env():
    my_path = pathlib.Path(__file__).parent.absolute()
    return Environment(loader=FileSystemLoader(my_path / "templates"))
