# Functional Tests

## Pre-requisites
Functional tests involve cloud resources which require authentication when run locally.

Check the following aws profiles presented in ~/.aws/config

```
[profile iambic_test_org_account/IambicHubRole]
credential_process = noq credential_process arn:aws:iam::580605962305:role/IambicHubRole

[profile iambic_test_org_spoke_account_1/iambic_image_builder]
credential_process = noq credential_process arn:aws:iam::442632209887:role/iambic_image_builder
```

## Warning, do not attempt to run tests in parallel!
First, the most time-consuming parts of the tests involve the setup.
This includes running import, setting up the config, and running `config.setup_aws_accounts`.
In an effort to reduce the run time the attributes this setup relates to are accessible globally.
Because these attributes can be updated in tests (like creating a new permission set) running parallel could cause a race condition.

Second, rate-limiting.
IAMbic commands are written in such a way to take into account throttling by the provider.
Running in parallel would cause certain calls to potentially exceed the limit resulting in intermittent failures.