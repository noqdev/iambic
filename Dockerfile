FROM public.ecr.aws/o4z3c2v2/iambic_container_base:1.0 as runtime-layer

# ######## REFERENCE YOUR OWN HANDLER HERE ########################
# CMD [ "main.app" ]```
######## ############################### ########################
# Install Requirements
# Install the function's dependencies
RUN pip3 install poetry awslambdaric argh watchdog
WORKDIR ${FUNCTION_DIR}
COPY pyproject.toml ${FUNCTION_DIR}
# Do not create virtualenv
RUN poetry config virtualenvs.create false
# Only install dependencies
RUN poetry install --no-root

# Copy function code
COPY . ${FUNCTION_DIR}

# Set the CMD to your handler (could also be done as a parameter override outside of the Dockerfile)
CMD [ "python", "-m", "iambic.lambda.app.handler" ]
