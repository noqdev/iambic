from noq_form.aws.iam.role.template_generation import (
    ROLE_RESPONSE_DIR,
    generate_aws_role_templates,
)
from noq_form.config.models import Config
from noq_form.core.logger import log


async def generate_templates(config_paths: str):
    response_dir_list = [ROLE_RESPONSE_DIR]
    configs = list()

    for config_path in config_paths:
        config = Config.load(config_path)
        config.set_account_defaults()
        configs.append(config)

    for response_dir in response_dir_list:
        response_dir.mkdir(parents=True, exist_ok=True)

    log.info("Generating AWS role templates.")
    await generate_aws_role_templates(configs)
