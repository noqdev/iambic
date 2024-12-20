# CEP 004 - Generic Git Provider Support

## Champion
smoy

## Summary
Quickly add support to other Git Provider that is not GitHub

## Rationale
The GitHub integration took sometime because it uses GitHub App interaction model. Such app
support is not universal in other Git providers. We want to maximize other Git provider support
with minimum complexity.

The most supported mechanism is git checkout repository using https. For the sake of concrete
examples, we will attempt to make this generic git provider at least support BitBucket,
AWS CodeCommit and GitLab. It's not limited to just these 3 providers. A Git provider
that supports git clone via https should be sufficient.

https git clone for private repository typically involves http basic auth. We
recommend users use an repository scoped token for authentication. We strongly
advise against using actual username, password combination. Access token is
less prone to re-use across other services.

Road Map
1. Launch import support with generic git provider.
2. Recruit additional help to implement Git Provider specific interactions.

Git Provider specific interactions

1. Each provider has different webhook event implementation details.
1. Each provider has different REST API
1. Each provider has different authentication + authorization model

## Customer Experience
1. User will still use `iambic setup` to install a lambda function
1. The lambda function will be driven by AWS EventBridge to periodic
import.
1. During install, user will need to provide the following

* username
* token
* clone url (must be https:// based)
* repo full name (typically company_name/repo_name )
* default branch name (typically main or master)

## Alternative
Is there alternative considered?

## Implementation
What's needed on the implementation?

## Compatibility concern
Is there any compatibility concern?