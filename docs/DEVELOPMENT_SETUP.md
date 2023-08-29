During development, create a virtual environment and install the project via poetry.

```console
python -m venv env
. env/bin/activate
pip install poetry
poetry install
```

To ensure any changes not introducing regression, please run `make test` within the virtual environment
with the project installed.

```console
# if you are not in an virtual environment already, source it
# . env/bin/activate
make test
```

`test` target will execute the unit tests that have no dependnecy on cloud resources.

`functional_test` target will execute the functional tests with dependency on specific cloud resources.
External developers have no access to them. Please defer to mintainers to verify functional tests.

