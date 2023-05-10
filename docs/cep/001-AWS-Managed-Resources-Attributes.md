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
