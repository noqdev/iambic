
## 0.5.1 (Target Date May 2nd, 2023)

PERMISSION CHANGES:
* IambicHubRole using a region agnostic resource definition in the SQS `IAMbicChangeDetectionQueue` permission (CloudFormation Template)

ENHANCEMENTS:
* The AWS region IAMbic should use is now configurable in the wizard.
* Added region awareness to cloud formation util functions.

BREAKING CHANGES:
* `AwsIdentityCenterPermissionSetTemplate` schema has changed. In particular, `permission_boundary.policy_arn` has become `permission_boundary.managed_policy_arn`. This is due PermissionSet API distinguishes attached
permission_boundary either owned by AWS or owned by Customer. To align with AWS API response, we have decided
to follow the AWS naming convention. The old name `permission_boundary.policy_arn` never quite work correctly
in `AwsIdentityCenterPermissionSetTemplate`. We decide to go with the breaking change route.

BUG FIXES:
* Fixed import of `AwsIdentityCenterPermissionSetTemplate` in which permission boundary is set to `managed_policy_arn`

THANKS:
* [perpil](https://github.com/perpil) for reporting [#372](https://github.com/noqdev/iambic/issues/372).

## 0.4.1 (May 1st, 2023)

PERMISSION CHANGES:
* IambicHubRole added SQS read/write access to queue named `IAMbicChangeDetectionQueue` to support IAM resource detection. [#355](https://github.com/noqdev/iambic/pull/355)
* IambicHubRole added sts:SetSourceIdentity to `IambicSpokeRole` to be compatible with Idp that enforce SetSourceIdentityForwarding [#361](https://github.com/noqdev/iambic/pull/361)

ENHANCEMENTS:
* Be compatible with Idp that enforces sts:SetSourceIdentity [reference](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp_control-access_monitor.html) [#361](https://github.com/noqdev/iambic/pull/361)

BUG FIXES:
* IAM resource detect mechanism cannot remove SQS message that is already been processed in `IAMbicChangeDetectionQueue` [#355](https://github.com/noqdev/iambic/pull/355)
* If environment variables contains AWS credentials, IAMbic wizard shall not ask what profile to write into configuration file. [#358](https://github.com/noqdev/iambic/pull/358)

THANKS:
* [perpil](https://github.com/perpil) for [#359](https://github.com/noqdev/iambic/pull/359) and multiple doc suggestions. [#363](https://github.com/noqdev/iambic/pull/363), and [#365](https://github.com/noqdev/iambic/pull/365)

## 0.3.0 (April 21, 2023)

BREAKING CHANGES:
* AWS templates containing account_id or account_name will need to be updated from `{{ account_id }}` to `{{ var.account_id }}` and from `{{ account_name }}` to `{{ var.account_name }}`. Alternatively, you can remove the files and re-import them.

You can use your favorite editor for find and replace, or give the following bash two-liner a try.

```bash
find . -type f -name "*.yaml" -print0 | xargs -0 sed -i '' -e 's/{{account_id}}/{{var.account_id}}/g'
find . -type f -name "*.yaml" -print0 | xargs -0 sed -i '' -e 's/{{account_name}}/{{var.account_name}}/g'
```

ENHANCEMENTS:
* Removed AWS package imports from core
* Standardized variable naming in templates
* Improved exception handling in the AWS package
* Cleaned up additional import only checks on AWS IAM role, user, and group models.

BUG FIXES:
* Resolved type error on merge template when new value is None.



## 0.2.0 (April 17, 2023)

Initial plan is to do a every 2-week release cycle.

ENHANCEMENTS:
* Improve memory footprint in templates reading
* Minimize I/O in templates reading
