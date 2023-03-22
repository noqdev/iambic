FROM public.ecr.aws/iambic/iambic_container_base:1.0

ARG FUNCTION_DIR="/app"


WORKDIR ${FUNCTION_DIR}

RUN mkdir -p ${FUNCTION_DIR}/iambic

# build the dependencies first to reuse the layer more often
COPY --chown=iambic:iambic poetry.lock ${FUNCTION_DIR}/poetry.lock
COPY --chown=iambic:iambic pyproject.toml ${FUNCTION_DIR}/pyproject.toml
COPY --chown=iambic:iambic README.md ${FUNCTION_DIR}/README.md

RUN adduser --system --user-group --home ${FUNCTION_DIR} iambic \
 && chown -R iambic:iambic ${FUNCTION_DIR} \
 && chmod -R 755 ${FUNCTION_DIR} \
 && chmod -R 777 ${FUNCTION_DIR}

RUN touch ${FUNCTION_DIR}/iambic/__init__.py

RUN /usr/local/bin/pip3 install poetry setuptools pip --upgrade \
 && /usr/local/bin/poetry install \
 && /usr/local/bin/poetry build \
 && /usr/local/bin/pip3 install awslambdaric

RUN /usr/local/bin/pip3 install ${FUNCTION_DIR}/dist/*.whl


# build the iambic package last
COPY --chown=iambic:iambic iambic/ ${FUNCTION_DIR}/iambic

RUN /usr/local/bin/poetry install \
 && /usr/local/bin/poetry build

RUN /usr/local/bin/pip3 uninstall iambic-core -y
RUN /usr/local/bin/pip3 install ${FUNCTION_DIR}/dist/iambic*.whl \
 && rm -rf ${FUNCTION_DIR}/dist

ENV IAMBIC_REPO_DIR /templates

VOLUME [ "/templates" ]

WORKDIR ${FUNCTION_DIR}

ENV IAMBIC_WEB_APP_DIR=${FUNCTION_DIR}/docs/web
ENV IAMBIC_DOCKER_CONTAINER=1

USER iambic:iambic

ENTRYPOINT [ "/usr/local/bin/python3", "-m", "iambic.main" ]
