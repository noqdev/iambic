import pathlib
from jinja2 import Environment, FileSystemLoader


def render_resource_changes(resource_changes):
    my_path = pathlib.Path(__file__).parent.absolute()
    env = Environment(loader=FileSystemLoader(my_path / 'templates'))
    template = env.get_template("resource_change.jinja2")
    return template.render(resource_changes=resource_changes)
