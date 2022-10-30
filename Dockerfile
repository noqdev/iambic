ARG FUNCTION_DIR="/app/"
ARG AWS_LINUX_VERSION="2022"
ARG PYTHON_VERSION="3.10.8"


FROM amazonlinux:${AWS_LINUX_VERSION} as python-layer

ARG PYTHON_VERSION

# install python
RUN yum update -y
RUN yum groupinstall "Development Tools" -y
RUN yum install libffi-devel bzip2-devel wget openssl openssl-devel sqlite-devel -y
RUN wget https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tgz
RUN tar -xf Python-${PYTHON_VERSION}.tgz
RUN cd Python-${PYTHON_VERSION}/ && \
    ./configure --enable-optimizations --enable-loadable-sqlite-extensions && \
    make install
RUN ln -s /Python-${PYTHON_VERSION}/python /usr/bin/python
RUN python -m pip install --upgrade pip


FROM amazonlinux:${AWS_LINUX_VERSION} as base-layer

RUN yum groupinstall "Development Tools" -y
RUN yum install git -y

# copy over python
ARG PYTHON_VERSION
COPY --from=python-layer /Python-${PYTHON_VERSION} /Python-${PYTHON_VERSION}
COPY --from=python-layer /usr/local/bin /usr/local/bin
COPY --from=python-layer /usr/local/lib /usr/local/lib
RUN ln -s /Python-${PYTHON_VERSION}/python /usr/bin/python

ARG FUNCTION_DIR
RUN mkdir -p ${FUNCTION_DIR}
WORKDIR ${FUNCTION_DIR}


FROM base-layer as build-layer

######## YOUR OWN SETUP PROCESS HERE ########################
# copy over requirements and install those
# COPY . .
# RUN pip install . --target "${FUNCTION_DIR}"

# copy over configuration and service code then install it
# COPY config/ ${FUNCTION_DIR}/config/
# COPY service/ ${FUNCTION_DIR}/
# RUN pip install . --target "${FUNCTION_DIR}"
######## ########################### ########################

# install lambda runtime interface client for python
RUN pip install awslambdaric --target "${FUNCTION_DIR}"


FROM base-layer as runtime-layer

# copy in the built dependencies
ARG FUNCTION_DIR
COPY --from=build-layer ${FUNCTION_DIR} ${FUNCTION_DIR}
WORKDIR ${FUNCTION_DIR}

# (optional) add lambda runtime interface emulator
ADD https://github.com/aws/aws-lambda-runtime-interface-emulator/releases/latest/download/aws-lambda-rie /usr/bin/aws-lambda-rie
RUN chmod 755 /usr/bin/aws-lambda-rie
# ENTRYPOINT [ "/usr/bin/aws-lambda-rie", "python", "-m", "awslambdaric" ]
ENTRYPOINT [ "python", "-m", "awslambdaric" ]

# ######## REFERENCE YOUR OWN HANDLER HERE ########################
# CMD [ "main.app" ]```
######## ############################### ########################
# Install Requirements
# Install the function's dependencies
RUN pip3 install poetry awslambdaric argh watchdog
WORKDIR ${LAMBDA_TASK_ROOT}
COPY pyproject.toml ${LAMBDA_TASK_ROOT}
# Do not create virtualenv
RUN poetry config virtualenvs.create false
# Only install dependencies
RUN poetry install --no-root

# Copy function code
COPY . ${LAMBDA_TASK_ROOT}

# Set the CMD to your handler (could also be done as a parameter override outside of the Dockerfile)
CMD [ "python", "-m", "iambic.lambda.app.handler" ]