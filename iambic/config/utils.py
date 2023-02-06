from __future__ import annotations

import asyncio
import os
import pathlib

from git import Repo

from iambic.aws.models import AWSAccount
from iambic.config.models import Config
from iambic.core.context import ctx
from iambic.core.git import clone_git_repos, get_origin_head
from iambic.core.iambic_enum import IambicManaged
from iambic.core.logger import log
from iambic.core.utils import gather_templates, yaml
from iambic.request_handler.apply import apply_changes
from iambic.request_handler.generate import GenerateTemplateScope, generate_templates


async def resolve_config_template_path(repo_dir: str) -> pathlib.Path:
    config_template_file_path = await gather_templates(repo_dir, "Core::Config")
    if len(config_template_file_path) == 0:
        raise RuntimeError(
            f"Unable to discover Iambic Configuration in {repo_dir}. "
            "Please create a configuration with the `NOQ::Core::Config` template type."
        )
    if len(config_template_file_path) > 1:
        raise RuntimeError(
            f"Too many NOQ::Core::Config templates discovered. Found ({len(config_template_file_path)}). Expected 1. Files: {','.join(config_template_file_path)}"
        )
    # Currently NOQ supports 1 configuration per repo
    return pathlib.Path(config_template_file_path[0])


async def load_template(repo_dir: str, plugins_configured: bool = False) -> Config:
    repo = Repo(repo_dir)
    previous_head = repo.head
    main_branch = get_origin_head(repo)
    if previous_head != main_branch:
        repo.git.checkout(main_branch)
    config_template_file_path = await resolve_config_template_path(repo_dir)
    c = Config(
        file_path=str(config_template_file_path),
        **yaml.load(open(str(config_template_file_path))),
    )
    repo.git.checkout(previous_head)
    if plugins_configured:
        await c.setup_aws_accounts()
    return c


async def store_template(config: Config, repo_dir: str, repo_name: str):
    # clone_git_repos will pull if repos exist versus cloning
    repo_path = pathlib.Path(repo_dir)
    try:
        config_path = await resolve_config_template_path(str(repo_path))
    except RuntimeError:
        config_path = repo_path / "config" / "config.yml"

    repo_base_path = repo_path.parent
    if not config.secrets:
        raise ValueError("No secrets configured")
    if repo_path.name not in [
        x.get("name") for x in config.secrets.get("git", {}).get("repositories", [])
    ]:
        raise ValueError(
            f"Invalidly formed configuration; expect config.secrets.git.repositories to have {repo_path.name}"
        )
    repos = await clone_git_repos(config, repo_base_path)
    if repos is None:
        raise RuntimeError(f"Unable to clone {repo_path}")
    os.makedirs(config_path.parent, exist_ok=True)
    repo = repos.get(repo_name)
    if not repo:
        raise RuntimeError(f"Cannot find {repo_name} in repos: {list(repos.keys())}")
    previous_head = repo.head
    main_branch = get_origin_head(repo)
    if previous_head != main_branch:
        repo.git.checkout(main_branch)

    config.write()
    # TODO: Setup a PR request
    repo.git.checkout(previous_head)


async def multi_config_loader(config_paths: list[str]) -> list[Config]:
    """Load multiple config files into a list of Config objects."""
    configs = []
    for config_path in config_paths:
        config = Config.load(config_path)
        configs.append(config)

    await asyncio.gather(*[config.setup_aws_accounts() for config in configs])

    identity_center_detail_set_tasks = []
    for config in configs:
        if config.aws and config.aws.accounts:
            identity_center_detail_set_tasks.extend(
                [
                    account.set_identity_center_details()
                    for account in config.aws.accounts
                ]
            )
    await asyncio.gather(*identity_center_detail_set_tasks)

    return configs


async def discover_new_aws_accounts(
    config: Config,
    config_account_idx_map: dict[str, int],
    orgs_accounts: list[list[AWSAccount]],
    repo_dir: str,
) -> bool:
    accounts_discovered = False
    run_apply = False
    run_import = False
    for org_accounts in orgs_accounts:
        for account in org_accounts:
            if config_account_idx_map.get(account.account_id) is None:
                accounts_discovered = True
                config.aws.accounts.append(account)
                log.warning(
                    "New AWS account discovered. Adding account to config.",
                    account_id=account.account_id,
                    account_name=account.account_name,
                )
                if account.iambic_managed not in [
                    IambicManaged.DISABLED,
                    IambicManaged.IMPORT_ONLY,
                ]:
                    run_apply = True

                if account.iambic_managed != IambicManaged.DISABLED:
                    run_import = True

    if run_apply:
        log.warning(
            "Applying templates to provision identities to the discovered account(s).",
        )
        templates = await gather_templates(repo_dir, "AWS.*")
        await apply_changes(config, templates, ctx)

    if accounts_discovered:
        config.write()

    return run_import


async def discover_aws_account_attribute_changes(
    config: Config,
    config_account_idx_map: dict[str, int],
    orgs_accounts: list[list[AWSAccount]],
) -> bool:
    account_updated = False
    run_import = False
    for org_accounts in orgs_accounts:
        for account in org_accounts:
            if (
                account_elem := config_account_idx_map.get(account.account_id)
            ) is not None:
                config_account = config.aws.accounts[account_elem]
                config_account_var_map = {
                    var["key"]: {"elem": idx, "value": var["value"]}
                    for idx, var in enumerate(config_account.variables)
                }

                if config_account.account_name != account.account_name:
                    log.warning(
                        "Updated AWS account name discovered. Updating account in config.",
                        account_id=account.account_id,
                        account_name=account.account_name,
                    )
                    account_updated = True
                    config.aws.accounts[
                        account_elem
                    ].account_name = account.account_name
                    if account.iambic_managed != IambicManaged.DISABLED:
                        run_import = True

                for org_account_var in account.variables:
                    if config_account_var := config_account_var_map.get(
                        org_account_var.key
                    ):
                        if config_account_var["value"] != org_account_var.value:
                            account_updated = True
                            log.warning(
                                "Mismatched variable on AWS account. Updating in config.",
                                account_id=account.account_id,
                                account_name=account.account_name,
                                variable_key=org_account_var.key,
                                discovered_value=org_account_var.value,
                                config_value=config_account_var["value"],
                            )
                            config.aws.accounts[account_elem].variables[
                                config_account_var["elem"]
                            ].value = org_account_var.value
                            if account.iambic_managed != IambicManaged.DISABLED:
                                run_import = True

    if account_updated:
        config.write()

    return run_import


async def aws_account_update_and_discovery(config: Config, repo_dir: str):
    if not config.aws_is_setup or not config.aws.organizations:
        return

    ctx.eval_only = False
    config_account_idx_map = {
        account.account_id: idx for idx, account in enumerate(config.aws.accounts)
    }

    orgs_accounts = await asyncio.gather(
        *[org.get_accounts() for org in config.aws.organizations]
    )
    import_new_account = await discover_new_aws_accounts(
        config, config_account_idx_map, orgs_accounts, repo_dir
    )
    import_updated_account = await discover_aws_account_attribute_changes(
        config, config_account_idx_map, orgs_accounts
    )
    if import_new_account or import_updated_account:
        log.warning(
            "Running import to regenerate AWS templates.",
        )
        await generate_templates([config], repo_dir, GenerateTemplateScope.AWS)
