from jinja2 import Environment, FileSystemLoader


def render_resource_changes(resource_changes):
    env = Environment(loader=FileSystemLoader('templates'))
    template = env.get_template("resource_change.jinja2")
    return template.render(resource_changes=resource_changes)
