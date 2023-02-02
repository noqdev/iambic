Security Consideration


1. Only main branch is allowed to assume web identity. This is to ensure only approved review changes are run with authentication.
2. WRITE_PR_COMMENT github token is accessible by any branches in the repo to enable auto planning by issuing comment. WRITE_PR_COMMENT has scope Pull Request Read & Write. This is a compromise. If its undesired, then the author or reviewer has to manually issue "iambic git-plan" to trigger the plan. This is due to workflow-run-A cannot spawn new workflow-run-B.
3. AUTO_IMPORT_GH_TOKEN github token is only accessible by production deployment rule. AUTO_IMPORT_GH_TOKEN token has scope Contents Read & Write. It's important to protect this token because it is used to import new changes into the repository.