ARG FUNCTION_DIR="/app"
ARG AWS_LINUX_VERSION="2022"
ARG PYTHON_VERSION="3.11.1"

ARG ARCH=
FROM ${ARCH}amazonlinux:${AWS_LINUX_VERSION} as python-layer

ARG PYTHON_VERSION

# install pytho
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

FROM ${ARCH}amazonlinux:${AWS_LINUX_VERSION} as base-layer

RUN yum groupinstall "Development Tools" -y \
 && yum install git -y

# copy over python
ARG PYTHON_VERSION
ARG FUNCTION_DIR="/app"
COPY --from=python-layer /Python-${PYTHON_VERSION} /Python-${PYTHON_VERSION}
COPY --from=python-layer /usr/local/bin /usr/local/bin
COPY --from=python-layer /usr/local/lib /usr/local/lib
RUN ln -s /Python-${PYTHON_VERSION}/python /usr/bin/python
RUN ln -s /Python-${PYTHON_VERSION}/pip3 /usr/bin/pip3

RUN mkdir -p ${FUNCTION_DIR}/iambic \
 && curl -sL https://dl.yarnpkg.com/rpm/yarn.repo -o /etc/yum.repos.d/yarn.repo \
 && yum install nodejs npm yarn -y

RUN adduser --system --user-group --home ${FUNCTION_DIR} iambic \
 && chown -R iambic:iambic ${FUNCTION_DIR} \
 && chmod -R 755 ${FUNCTION_DIR}

USER iambic:iambic

RUN mkdir -p "${FUNCTION_DIR}"

COPY --chown=iambic:iambic iambic ${FUNCTION_DIR}/iambic
COPY --chown=iambic:iambic docs ${FUNCTION_DIR}/docs
COPY --chown=iambic:iambic poetry.lock ${FUNCTION_DIR}/poetry.lock
COPY --chown=iambic:iambic pyproject.toml ${FUNCTION_DIR}/pyproject.toml
COPY --chown=iambic:iambic README.md ${FUNCTION_DIR}/README.md

ENV IAMBIC_REPO_DIR /templates
ENV PATH=${PATH}:${FUNCTION_DIR}/.local/bin
VOLUME [ "/templates" ]

WORKDIR ${FUNCTION_DIR}/docs

RUN yarn

EXPOSE 3000

WORKDIR ${FUNCTION_DIR}

ENV POETRY_VIRTUALENVS_PATH=${FUNCTION_DIR}/.local
RUN pip install poetry \
 && poetry update \
 && poetry install

ENV PYTHONPATH=${PYTHONPATH}:${FUNCTION_DIR}/.local/lib/python3.11/site-packages

ENTRYPOINT [ "python", "-m", "iambic.main" ]
