from __future__ import annotations

import urllib


class GenericGitClient(object):
    def __init__(self, secrets):
        """
        secrets has to be a dictionary format as the following

        username: non-empty string (before url_quote_plus)
        token: non-empty string (before url_quote_plus)
        clone_url: typically https://git-provider.com/group/repo_name (must be https:// protocol)
        default_branch_name: typically main or master
        repo_full_name: must be in group/repo format (like example_corp/iambic-templates)
        """
        self.username = secrets["username"]
        self.token = secrets["token"]
        self.clone_url = secrets["clone_url"]
        self.default_branch_name = secrets["default_branch_name"]
        self.repo_full_name = secrets["repo_full_name"]

        # we should always take the precaution someone give us a non-https url
        assert self.clone_url.startswith("https://")
        # we should always take the precaution someone did not sneak an @ in the url
        # that may accidentally be a password. A simple assert may print the potential
        # url with password
        if "@" in self.clone_url:
            raise ValueError("@ is detected in url")
        self.clone_url_without_protocol = self.clone_url.replace("https://", "")

    @property
    def repo_url(self):
        encoded_username = urllib.parse.quote_plus(self.username)
        encoded_token = urllib.parse.quote_plus(self.token)
        return f"https://{encoded_username}:{encoded_token}@{self.clone_url_without_protocol}"


def create_git_client(secrets):
    return GenericGitClient(secrets)
