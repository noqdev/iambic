FROM public.ecr.aws/iambic/iambic_container_base:1.0

ARG FUNCTION_DIR="/app"


WORKDIR ${FUNCTION_DIR}

RUN mkdir -p ${FUNCTION_DIR}/iambic

RUN adduser --system --user-group --home ${FUNCTION_DIR} iambic \
    && chown -R iambic:iambic ${FUNCTION_DIR} \
    && chmod -R 755 ${FUNCTION_DIR} \
    && chmod -R 777 ${FUNCTION_DIR}

# build the dependencies first to reuse the layer more often
COPY --chown=iambic:iambic poetry.lock pyproject.toml README.md ${FUNCTION_DIR}/

RUN /usr/local/bin/pip3 install poetry setuptools pip --upgrade \
    && poetry config virtualenvs.create false --local \
    && poetry export -f requirements.txt --output requirements.txt \
    && /usr/local/bin/pip3 install -r requirements.txt \
    && /usr/local/bin/pip3 install awslambdaric

# build the iambic package last
COPY --chown=iambic:iambic iambic/ ${FUNCTION_DIR}/iambic

RUN /usr/local/bin/poetry install \
    && rm -rf ${FUNCTION_DIR}/dist

ENV IAMBIC_REPO_DIR /templates

VOLUME [ "/templates" ]

WORKDIR ${FUNCTION_DIR}

ENV IAMBIC_WEB_APP_DIR=${FUNCTION_DIR}/docs/web
ENV IAMBIC_DOCKER_CONTAINER=1

USER iambic:iambic

ENTRYPOINT [ "/usr/local/bin/python3", "-m", "iambic.main" ]
