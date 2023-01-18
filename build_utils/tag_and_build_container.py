from __future__ import annotations

import sys

import toml


def get_current_version():
    with open("./pyproject.toml", "r") as f:
        iambic_toml = toml.load(f)
    version = iambic_toml["tool"]["poetry"]["version"]
    print(version)


def bump_version():
    with open("./pyproject.toml", "r") as f:
        iambic_toml = toml.load(f)
    current_version_string = iambic_toml["tool"]["poetry"]["version"]
    versions = current_version_string.split(".")
    patch_version = int(versions[2])
    patch_version = patch_version + 1
    versions[2] = str(patch_version)
    new_version_string = ".".join(versions)
    iambic_toml["tool"]["poetry"]["version"] = new_version_string
    with open("./pyproject.toml", "w") as f:
        toml.dump(iambic_toml, f)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise Exception("You must pass a command")
    command = sys.argv[1]
    command_to_func = {
        "print-current-version": get_current_version,
        "bump-version": bump_version,
    }
    command_to_func[command]()
