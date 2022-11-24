import asyncio
import os
from pathlib import Path

from git import Repo
from git.exc import GitCommandError
from github import Github
from pydantic import BaseModel as PydanticBaseModel
from pydantic.fields import Any

from iambic.core.logger import log
from iambic.core.utils import aio_wrapper


class IambicRepo:
    def __init__(
            self,
            tenant: str,
            repo_name: str,
            repo_uri: str,
            request_id: str = None,
            requested_by: str = None,
            use_request_branch: bool = False,
    ):
        self.tenant = tenant
        self.repo_name = repo_name
        self.repo_uri = repo_uri
        self.request_id = request_id
        self.requested_by = requested_by
        self.use_request_branch = use_request_branch
        self._default_file_path = Path(
            f"/data/tenant_data/{self.tenant}/iambic_template_repos/{self.repo_name}"
        )
        self.repo = None
        self._default_branch = None

        if use_request_branch:
            assert request_id
            assert requested_by

    async def set_repo(self):
        if os.path.exists(self.default_file_path):
            self.repo = Repo(self.default_file_path)
        else:
            self.repo = await aio_wrapper(Repo.clone_from, self.repo_uri, self.default_file_path)

    async def create_branch(self, request_id: str, requested_by: str, files: list):
        raise NotImplementedError

    async def update_branch(self, files: list):
        raise NotImplementedError

    async def delete_branch(self):
        raise NotImplementedError

    @property
    def default_file_path(self):
        return self._default_file_path

    @property
    def request_file_path(self):
        assert self.request_id
        assert self.requested_by
        return Path(
            f"/data/tenant_data/{self.tenant}/iambic_template_user_workspaces/{self.requested_by}/{self.repo_name}/noq-self-service-{self.request_id}"
        )

    @property
    def file_path(self):
        if not self.use_request_branch:
            return self.default_file_path
        else:
            return self.request_file_path

    @property
    def default_branch(self):
        if not self._default_branch:
            self._default_branch = next(
                ref for ref in self.repo.remotes.origin.refs if ref.name == "origin/HEAD"
            ).ref.name

        return self._default_branch


class GitComment(PydanticBaseModel):
    id: str
    user: str
    body: str
    in_reply_to_id: str = None


class PullRequestFile(PydanticBaseModel):
    filename: str
    status: str
    additions: int
    patch: str
    body: str


class BasePullRequest(PydanticBaseModel):
    tenant: str
    repo_name: str
    pull_request_id: int = None
    request_id: str = None
    requested_by: str = None

    title: str = None
    description: str = None
    comments: list[GitComment] = None
    files: list[PullRequestFile] = None
    mergeable: bool = None

    pr_provider: Any = None
    repo: Any = None

    async def load_pr(self):
        raise NotImplementedError

    async def add_comment(self, comment: str):
        raise NotImplementedError

    async def update_comment(self, comment_id: int, body: str):
        raise NotImplementedError

    async def delete_comment(self, comment: str):
        raise NotImplementedError

    async def _create_request(self):
        raise NotImplementedError

    async def create_request(
            self,
            title: str,
            description: str,
            files: list,
    ):
        self.title = title
        self.description = description
        await self.repo.create_branch(self.request_id, self.requested_by, files)
        await self._create_request()

    async def _update_request(self):
        raise NotImplementedError

    async def update_request(
            self,
            description: str = None,
            files: list = None,
    ):
        if description and self.description != description:
            self.description = description
            await self._update_request()

        if files:
            await self.repo.update_branch(files)
            await self._update_request()

    async def merge_request(self):
        raise NotImplementedError

    async def reject_request(self):
        raise NotImplementedError

    async def get_request_details(self):
        # Set title, description, comments, etc.
        raise NotImplementedError


class GitHubPullRequest(BasePullRequest):

    def __init__(self, access_token: str, *args, **kwargs):
        super(BasePullRequest, self).__init__(*args, **kwargs)
        self.pr_provider = Github(access_token).get_repo(kwargs["repo_name"])
        log.warning(self.pr_provider)

    async def load_pr(self):
        assert self.pull_request_id
        pr_details = await aio_wrapper(self.pr_provider.get_pull, self.pull_request_id)
        self.comments = []
        for comments in (await asyncio.gather(
                aio_wrapper(pr_details.get_comments),
                aio_wrapper(pr_details.get_issue_comments),
        )):
            for comment in comments:
                self.comments.append(
                    GitComment(
                        id=comment.id,
                        user=comment.user.login,
                        body=comment.body,
                        in_reply_to_id=getattr(comment, "in_reply_to", None)
                    )
                )

        self.files = []
        for file in (await aio_wrapper(pr_details.get_files)):
            log.warning(getattr(file, "_rawData"))
            self.files.append(
                PullRequestFile(
                    body="TODO",
                    **getattr(file, "_rawData")
                )
            )

        self.title = pr_details.title
        self.description = pr_details.body

    async def add_comment(self, comment_id: int):
        raise NotImplementedError

    async def update_comment(self, comment_id: int, body: str):
        raise NotImplementedError

    async def delete_comment(self, comment_id: int):
        raise NotImplementedError

    async def _create_request(self):
        raise NotImplementedError

    async def _update_request(self):
        raise NotImplementedError

    async def merge_request(self):
        raise NotImplementedError

    async def reject_request(self):
        raise NotImplementedError

    async def get_request_details(self):
        # Set title, description, comments, etc.
        raise NotImplementedError


"""
tenant: str
repo_uri: str
default_branch: str
pull_request_id: int
request_id: str = None
requested_by: str = None
"""


async def runner():
    sample_pr = GitHubPullRequest(
        access_token="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",
        repo_name="noqdev/iambic",
        tenant="corp_noq_dev",
        pull_request_id=28,
        request_id="feat/en-1415-cloudformation-syntax",
        requested_by="will@noq.dev",
    )
    await sample_pr.load_pr()

    print(sample_pr.pr_provider.git_url)

    # import json
    #
    # print(json.dumps(sample_pr.dict(exclude={"pr_provider", "repo"}), indent=2))


asyncio.run(runner())


"""
IambicRepo is used to create a branch, update a branch, and delete a branch.
This includes checking out the repo, making trees, cleaning up trees and refreshing the repo dir
In other words IambicRepo is the interface to the repo itself and the branches

BasePullRequest is a PR interface base class inherited by supported Git Providers. Currently this is only github.
It is meant to represent a PR in a way meaningful to the new SaaS/Iambic request.


When a request is created:
    A Noq Request is created including its UUID
    An instance of the IambicRepo is used to create a tree and a branch that contains the request changes.
    A PR is created using the IambicRepo instance defined above.
    The Noq Request is updated to include the PR ID and potentially other metadata about the PR.


When a request is made to view the request details:
    An instance of the ProviderPullRequest is created with the Request PR metadata.
    Call ProviderPullRequest.load_pr() to load the PR details into the ProviderPullRequest instance.
    Return ProviderPullRequest().dict(exclude={"pr_provider", "repo"}


When a request is updated (Any changes or the approval of a request):
    An instance of the ProviderPullRequest is created with the Request PR metadata.
    Call ProviderPullRequest().update_request() to update the PR with the new changes.
    The call will also update the IambicRepo instance with the new changes.



Issues:
- The hope was to leverage the comments on the PR but that may be difficult because there is no way to add comments
- Repo.clone_from requires a uri but that requires credentials to be embedded in the uri. This is not ideal.
- The flow can be a bit confusing 
- Probably need some git provider auth class. Not a big deal just wanted to capture that somewhere.



"""



"""Notes

Noq should clone this repo in a namespace that is logically separated from other tenants
Noq should perform validation on the tenant and repo name. 
Noq should make sure to make the location flexible, so we can store other things in tenant storage in the future, and not worry about name collisions.
Noq should presume that these paths may be visible to end-users, and should not 
Noq should take the utmost care not to violate tenant security logical separation by preventing things like relative paths (Remember, the customer is in control of the Git repo. What can they do that is malicious?)
The main repository path (example below) should always be on the default branch
Customer is responsible for Git repo, could they do anything malicious with pre-commit hooks?

Path Convention Proposal: 

tenant = corp_noq_dev
repo = noq-templates
This path will always be on the default branch

Path: 

/data/tenant_data/corp_noq_dev/iambic_template_repos/noq-templates/...

Like the main repo, we should provide a separated namespace for the user on disk
We will need to support multiple branches per user, since they may have pending requests and want to submit more distinct requests
We should make it impossible to have collisions by namespace
Can we set git email and git name on a per-branch basis? If so, we can let reviewers identify who made a file in `git blame` Historical tracking is a dream.

Tenant: corp_noq_dev
User: curtis@noq.dev
Repo: noq-templates
Request Number: Request UUID? - e0d0e5b9-3b0a-4920-9ae3-f2b810bd702f

Path for the file request:  /data/tenant_data/corp_noq_dev/iambic_template_user_workspaces/curtis@noq.dev/noq-templates/noq-self-service-e0d0e5b9-3b0a-4920-9ae3-f2b810bd702f/...

Git worktree command: 

# In the main repo directory
git worktree add /data/tenant_data/corp_noq_dev/iambic_template_user_workspaces/curtis@noq.dev/noq-templates/noq-self-service-e0d0e5b9-3b0a-4920-9ae3-f2b810bd702f/ -b noq-self-service-e0d0e5b9-3b0a-4920-9ae3-f2b810bd702f

We then need to:
`git add` every file that was changed,
`git commit`, # When user is ready to submit request and gives us a message
# Git Message will be canned, like `Self-Service Request for <user>` 
# Justification will be added as a PR Description since it might be long. 
`git push -u origin noq-self-service-e0d0e5b9-3b0a-4920-9ae3-f2b810bd702f`
"""
