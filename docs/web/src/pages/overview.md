
# Introduction to Iambic

IAMbic is an open-source language that simplifies the process of monitoring and managing Cloud IAM for AWS, Okta, and Google. The core objectives of Iambic are as follows:

1. Allow users to easily understand and manage human and cloud identities, as well as their permissions, in one place.
2. Provide breakglass and JIT access to cloud identities
3. Change access and permissions with a single pull request
4. Round-trip configurations from Cloud to Config at any time

... All without hiding behind a proprietary vendor database.

## Supported Integrations

Iambic currently integrates with AWS, Okta, and Google.

For AWS, Noq supports AWS permission sets and IAM roles

Propagating changes

Interval check to remediate partials

If someone approved a change and it only partially succeeded, when the import command runs, it updates what is in git to say it was only a partial success.

We need to sit down and think about which path is the least bad.

If what is in main is supposed to reflect what is in reality, then we'll either be wrong that we're not incorporating the changes that were merged in that were partially successful, or we will be wrong that we merged changes that partially failed.

Ideal world: We keep track of all changes, there is a lot of complexity and added compute for trying to revert, and we have more opportunities for partial failures with reverting.

What we can do: On partial success, we merge the PR to main and kick off import, and associate it with the PR.

We can't bottleneck the merging of it

We can create a scenario where someone operating off of an invalid state.  Conversation between Will, Curtis, and Steven. Once we find a few different paths, we can inquire with Noah and Rohit. These are the ways we can approach it.

Biggest issue: Differentiating recoverable and non-recoverable failures. If we can interpolate the error that comes in from the provider to see if we can or cannot recover. If the non-recoverable failure occurs in a subset of a partial success.

Full list of Options:

    1. On partial fail: Merge the change, and comment on the PR

    2. On partial fail: Don't merge the change, comment on the PR

    3.
