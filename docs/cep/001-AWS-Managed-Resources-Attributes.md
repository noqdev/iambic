# CEP 001 - Differentiate IAM resources that should be not be changed by user

## Summary
Introduce attribute to differentiate IAM resources that should not be modified by AWS account administrators.

## Rationale
IdentityCenter Account Association generates IAM roles that are managed by
IdentityCenter. Although such IAM roles are included by IAMbic import. If they
are modified by users, it will diverage from the intend.

IAM service-link roles are managed by AWS, and cannot be edited. Edit operations
will generate API error.

By introducing an attribute `cloud_provider_managed_resource`, type `boolean`, the
IAMbic business logic can introduce special handling for them.

For example, these resources should be marked as `iambic_managed: IMPORT_ONLY`.
In addition, we can introduce a particular default directory location to store such
managed_resources.

## Customer Experience
For Identity Center permissions set that `n` associated accounts, AWS generates `n`
corresponding IAM roles. One for each associated account. Currently, they appear
alongside other regular roles. By default, we can use the `path` information to
place these roles.

A role created due to Identity Center as a path like `/aws-reserved/sso.amazonaws.com/`
We can place the role in `<relative_directory>/aws-reserved/sso.amazonaws.com`.

Using `path` information serves as a natural grouping user experience.

There is concern about the extra number of file bloats. The pillar of IAMbic is to
maintain source of truth. Those IAM roles are actual artifacts included in the list
API. So they really should be kept inside template directory. This CEP attempts
to improve the user experience, such that permission sets and other service-linked
roles does not clutter the other IAM roles that customer typically needs to maintain.

Each IAM resources is represented by a single file is a compromise of
maintain GitOps workflow in which developer goes through git flow to make changes
of IAM postures. Git does scale to the size of Microsoft Windows development. In
performance critical flow, we can later extend with a real DBMS for fast query.
File can be see as a duality of rows represented inside a DBMS.

## Alternative
[Issue #388](https://github.com/noqdev/iambic/issues/388) suggests not even import
them in the first place. (The import preference will be configurable). I argue that
breaks the abstraction that IAMbic maintains a catalog that is sufficient to run
analysis against security posture. Not having such managed resource definition will
limit posture analysis. The user experience desired is not having them next to the
resources that users need to edit.

## Implementation
* We need to introduce some classification logic likely based on `path`.
* Suggest alternative directory location for manageed resources.
* (future) flag it's not possible to make changes to managed resources in plan.

## Compatibility concern
1. The new attribute should be optional to make existing templates not crash the new
version of IAMbic.
