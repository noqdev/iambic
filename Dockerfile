ARG FUNCTION_DIR="/app"
ARG AWS_LINUX_VERSION="2022"
ARG PYTHON_VERSION="3.11.1"

ARG ARCH=
FROM ${ARCH}amazonlinux:${AWS_LINUX_VERSION} as python-layer

ARG PYTHON_VERSION

# install python
RUN yum update -y \
 && yum groupinstall "Development Tools" -y \
 && yum install libffi-devel bzip2-devel wget openssl openssl-devel sqlite-devel -y \
 && wget https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tgz \
 && tar -xf Python-${PYTHON_VERSION}.tgz \
 && cd Python-${PYTHON_VERSION}/ && \
    ./configure --enable-optimizations --enable-loadable-sqlite-extensions && \
    make install \
 && ln -s /Python-${PYTHON_VERSION}/python /usr/bin/python \
 && python -m ensurepip --upgrade \
 && python -m pip install --upgrade pip


FROM ${ARCH}amazonlinux:${AWS_LINUX_VERSION} as build-layer

RUN yum groupinstall "Development Tools" -y \
 && yum install git -y

# copy python to the necessary locations
ARG PYTHON_VERSION
ARG FUNCTION_DIR="/app"
COPY --from=python-layer /Python-${PYTHON_VERSION} /Python-${PYTHON_VERSION}
COPY --from=python-layer /usr/local/bin /usr/local/bin
COPY --from=python-layer /usr/local/lib /usr/local/lib
RUN ln -s /Python-${PYTHON_VERSION}/python /usr/bin/python
RUN ln -s /Python-${PYTHON_VERSION}/pip3 /usr/bin/pip3

COPY --chown=iambic:iambic iambic/ ${FUNCTION_DIR}/iambic
COPY --chown=iambic:iambic poetry.lock ${FUNCTION_DIR}/poetry.lock
COPY --chown=iambic:iambic pyproject.toml ${FUNCTION_DIR}/pyproject.toml
COPY --chown=iambic:iambic README.md ${FUNCTION_DIR}/README.md

WORKDIR ${FUNCTION_DIR}

RUN pip install poetry setuptools pip --upgrade \
 && poetry install \
 && poetry build


FROM ${ARCH}amazonlinux:${AWS_LINUX_VERSION} as runtime-layer

# copy python to the necessary locations
ARG PYTHON_VERSION
ARG FUNCTION_DIR="/app"
COPY --from=python-layer /Python-${PYTHON_VERSION} /Python-${PYTHON_VERSION}
COPY --from=python-layer /usr/local/bin /usr/local/bin
COPY --from=python-layer /usr/local/lib /usr/local/lib
RUN ln -s /Python-${PYTHON_VERSION}/python /usr/bin/python
RUN ln -s /Python-${PYTHON_VERSION}/pip3 /usr/bin/pip3

RUN yum install git shadow-utils -y

COPY --from=build-layer ${FUNCTION_DIR}/dist ${FUNCTION_DIR}/dist

RUN pip install ${FUNCTION_DIR}/dist/*.whl \
 && rm -rf ${FUNCTION_DIR}/dist

COPY --chown=iambic:iambic docs/ ${FUNCTION_DIR}/docs

RUN mkdir -p ${FUNCTION_DIR}/iambic \
 && curl -sL https://dl.yarnpkg.com/rpm/yarn.repo -o /etc/yum.repos.d/yarn.repo \
 && yum install nodejs npm yarn -y

RUN adduser --system --user-group --home ${FUNCTION_DIR} iambic \
 && chown -R iambic:iambic ${FUNCTION_DIR} \
 && chmod -R 755 ${FUNCTION_DIR} \
 && chmod -R 777 ${FUNCTION_DIR}

ENV IAMBIC_REPO_DIR /templates

VOLUME [ "/templates" ]

WORKDIR ${FUNCTION_DIR}/docs/web

RUN yarn \
 && yarn install --frozen-lockfile

WORKDIR ${FUNCTION_DIR}

ENV PYTHONPATH=${PYTHONPATH}:${FUNCTION_DIR}/.local/lib/python3.11/site-packages
ENV IAMBIC_WEB_APP_DIR=${FUNCTION_DIR}/docs/web
ENV IAMBIC_DOCKER_CONTAINER=1

USER iambic:iambic

ENTRYPOINT [ "python", "-m", "iambic.main" ]
