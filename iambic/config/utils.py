import os
import pathlib
from iambic.config.models import Config
from iambic.core.git import clone_git_repos, main_or_master
from iambic.core.logger import log
from iambic.core.utils import gather_templates, yaml


async def resolve_config_template_path(repo_dir: str) -> pathlib.Path:
    config_template_file_path = await gather_templates(repo_dir, "Core::Config")
    if len(config_template_file_path) > 1 or len(config_template_file_path) == 0:
        raise RuntimeError(f"Invalid number of NOQ::Core::Config templates found ({len(config_template_file_path)}), currently only support 1")
    # Currently NOQ supports 1 configuration per repo
    return pathlib.Path(config_template_file_path[0])


async def load_template(repo_dir: str, plugins_configured: bool = False) -> Config:
    config_template_file_path = await resolve_config_template_path(repo_dir)
    c = Config(file_path=str(config_template_file_path), **yaml.load(open(str(config_template_file_path))))
    if plugins_configured:
        c.configure_plugins()
    return c


async def store_template(config: Config, repo_dir: str, repo_name: str):
    # clone_git_repos will pull if repos exist versus cloning
    repo_path = pathlib.Path(repo_dir)
    config_path = repo_path / "config" / "config.yml"
    repo_base_path = repo_path.parent
    if not config.secrets:
        raise ValueError("No secrets configured")
    if not repo_path.name in config.secrets.get("git", {}).get("repositories", []):
        raise ValueError(f"Invalidly formed configuration; expect config.secrets.git.repositories to have {repo_path.name}")
    repos = await clone_git_repos(config, repo_base_path)
    if repos is None:
        raise RuntimeError(f"Unable to clone {repo_path}")
    os.makedirs(config_path.parent, exist_ok=True)
    repo = repos.get(repo_name)
    if not repo:
        log.error(f"Cannot find {repo_name} in repos: {list(repos.keys())}")
    repo = repos[repo_name]
    previous_head = repo.head
    main_branch = main_or_master(repo)
    if previous_head != main_branch:
        repo.git.checkout(main_branch)
    config_template_file_path = config_path
    with open(config_template_file_path, 'w') as fp:
        yaml.dump(config.dict(), fp)
    # TODO: Setup a PR request
    repo.git.checkout(previous_head)
