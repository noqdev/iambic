# CEP 002 - GitHub App Interactions Protocol

## Summary

Outlines how a different GitHub app can interact with the IAMbic
GitHub App integration

## Rationale

IAMbic GitHub App is responsible for continuous integration and continuous
delivery. By itself, it's meant to be an assistant for human developers.
It automatically plans changes in the pull requests and made comments back
to pull requests. Pull requests authors and reviewers decide when to apply
the changes.

If a different GitHub App (hereby known as GA2) needs to interact with the pull request flow, it
needs additional information beyond what GitHub pull request provides. For
example, GA2 is a enterprise application that opens a pull request on iambic templates repository, we need
a mechanism to approve the pull request without a developer interacting with GitHub.

GitHub Pull Requests prohibits pull request author to approve its own requests.
We need to extend IAMBic GitHub App to submit pull request review with "Approve Event".
In addition, the authenticity and authorization needs to be established between
IAMbic GitHub app and GA2 because most environments need to control changes
within their IAMbic templates to be in compliance.

## Customer Experience
Customer that depends on GA2 typically don't use GitHub interface. We need to support
GA2 to drive the pull request forward without customer interacting directly with GitHub.

GA2 can rely on a separate set of user experience outside of GitHub.

## Alternative
Is there alternative considered?

## Implementation

### approve

GA2 submits a signed comment in the following format.

```
iambic approve
<free form>
<!--signed_payload_in_jwt_format-->
```

`signed_payload_in_jwt_format` is a json payload with the following require attributes
in ES256 algorithm.

```json
{
    "repo": "example.com/iambic-templates",
    "pr": 1,
    "signee": [
        "user1@example.org",
        "user2@example.org",
    ],
}
```

### errors

If `iambic apply` fails, it contains a footer in the comment body payload as

```
free form error data
<!--iambic/apply/error-->
```

Currently, we have not yet signed the footer. It's possible to cause denial of service
error to GA2 if malicious identity makes comment with the same footer and GA2
reacts to such footer unconditionally.

A possible improvement is to establish signature verification from IAMbic GitHub App to GA2.

## Compatibility concern
As of 2023-06-22, there is no compatibility concern.