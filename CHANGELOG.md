
# Change Log

## 0.9.6 (Jun 15, 2023)

BUG FIXES:

* Fixed IAMbic import errors when AWS Organization that has no permission sets in IdentityCenter [#459](https://github.com/noqdev/iambic/pull/459)
* Fixed broken links on README.md [#465](https://github.com/noqdev/iambic/pull/465)
* Fixed import issue when AWS policy document uses `Id` element [#464](https://github.com/noqdev/iambic/pull/464)

ENHANCEMENTS:

* Improve IAMbic wizard prompting when AWS Organization has not yet enabled trusted access for CloudFormation StackSets. [#459](https://github.com/noqdev/iambic/pull/459)
* Only configure structlog if it's not already configured. More friendly when `iambic-core` is used as a library [#462](https://github.com/noqdev/iambic/pull/462)

THANKS:
* `sidick` for reporting AWS Organization import issue when there is no permission sets in IdentityCenter [#460](https://github.com/noqdev/iambic/issues/460)
* `sidick` for reporting lack of prompts when AWS Organization has not yet enabled trusted organization access for Cloudformation StackSets. [#458](https://github.com/noqdev/iambic/issues/458)
* `sourcefrog` for contribution in fixing README [#461](https://github.com/noqdev/iambic/pull/461)
* `sidick` for reporting AWS Role import issue when `Id` element is used [#463](https://github.com/noqdev/iambic/issues/463)

## 0.9.1 (Jun 9, 2023)

BUG FIXES:
* Fixed [#419](https://github.com/noqdev/iambic/issues/419): Deleted file should not be removed again during Git workflow [#441](https://github.com/noqdev/iambic/pull/441)
* Fixed functional test [#451](https://github.com/noqdev/iambic/pull/451)
* Skip a key from new_model if old_model already mark it as metadata [#453](https://github.com/noqdev/iambic/pull/453)
* Do not override logging settings when used as library [#454](https://github.com/noqdev/iambic/pull/454)

ENHANCEMENTS:
* Bump `cryptography` from `39.0.1` to `41.0.1`  [#443](https://github.com/noqdev/iambic/pull/443)
* Skip wizard prompts if AWS SDK can verify settings [#444](https://github.com/noqdev/iambic/pull/444)
* Move module level templates symbol to config to allow ease of use of `iambic-core` as library [#440](https://github.com/noqdev/iambic/pull/440)
* Dependency Cleanup [#448](https://github.com/noqdev/iambic/pull/448)
* Included empty tags dict when decribing role without tags [#449](https://github.com/noqdev/iambic/pull/449)
* Implemented "iambic approve" for GitHub workflow [#452](https://github.com/noqdev/iambic/pull/452). It's now possible to have IAMbic GitHub integration to approve PR. The workflow allows another GitHub App to open a PR and mark the PR as `approved`. See the pull request for the full discussion on security considerations. It's secure by default, because without an actual configuration with a public/private key, the IAMbic GitHub integration's approve command will not work.

DOCS:
* Create 001-AWS-Managed-Resources-Attributes [#395](https://github.com/noqdev/iambic/pull/395). We recommend contributor to write up the design prior to creating a large pull request, so the community can give feedback prior to a significant change.
* Improve GitHub App creation docs to have most of the settings included in the query params [#402](https://github.com/noqdev/iambic/pull/402)


THANKS:
* `mxw-sec` for reporting issue [#419](https://github.com/noqdev/iambic/issues/419) regarding AWS IAM Delete File issue Github APP
* `mxw-sec` for discussing how to improve GitHub App creation using GitHub App Manifest
* `datfinesoul` for reporting issue [#405](https://github.com/noqdev/iambic/issues/405) regarding Automatically Detect Management Account for AWS Organizations to confirm an existing prompt.
* `mikegrima` for contributing [#448](https://github.com/noqdev/iambic/pull/448). This shrinks the install dependencies when using `iambic-core` as library.
* `mikegrima` for contributing [#449](https://github.com/noqdev/iambic/pull/449). This makes AWS role tags before/after value much easier to compare by handling boto3 quarks.

## 0.8.1 (May 30, 2023)

BUG FIXES:

* Explicitly setting `account_id` and `account_name` variables during AWS Account Setup Wizard [#430](https://github.com/noqdev/iambic/pull/430)
* Create iambic docker user before assigning file permissions [#435](https://github.com/noqdev/iambic/pull/435)
* Handled unbound changes variable on plan_git_changes [#434](https://github.com/noqdev/iambic/pull/434)
* Detect changes between policy documents [#436](https://github.com/noqdev/iambic/pull/436)
* More robust yaml comments interaction between templates and subsequent import [#437](https://github.com/noqdev/iambic/pull/437)

ENHANCEMENTS:

* AWS SCP (Service Control Policy) support. [#384](https://github.com/noqdev/iambic/pull/384)
* Development experience changes on removing pytest.ini for ease for run-and-debug [#428](https://github.com/noqdev/iambic/pull/428)
* Docs for AWS Change Detection [#429](https://github.com/noqdev/iambic/pull/429)
* Docs for IAMbic gist repo usage [#432](https://github.com/noqdev/iambic/pull/432)
* SCP Quickstart Docs [#433](https://github.com/noqdev/iambic/pull/433)

## 0.7.18 (May 24th, 2023)

BUG FIXES:

* Fix merge model int handling (impact subsequent importing) [#410](https://github.com/noqdev/iambic/pull/410)
* Fixed wizard prompt when editing an AWS account. [#415](https://github.com/noqdev/iambic/pull/415)
* Fix missing tags on IambicSpokeRole in the management account [#416](https://github.com/noqdev/iambic/pull/416)
* Fix change detection setup for isolated runs [#417](https://github.com/noqdev/iambic/pull/417)
* Ignore extra fields provided by Azure AD [#424](https://github.com/noqdev/iambic/pull/425)
* Upgrade requests from 2.30.0 to 2.31.0 [#425](https://github.com/noqdev/iambic/pull/425)
* Move IAMbic default docker image to ship with Python 3.10.8 instead of 3.11.1 Setup Wizard [#427](https://github.com/noqdev/iambic/pull/427)

ENHANCEMENTS:

* Development experience changes on customizing hub and spoke role  [#422](https://github.com/noqdev/iambic/pull/422)
* Docs referencing IAMOps flow [#420](https://github.com/noqdev/iambic/pull/420)
* Development experience changes on requiring greater than 75% coverage [#422](https://github.com/noqdev/iambic/pull/422)

THANKS:

* `datfinesoul` for reporting missing tags on IambicSpokeRole creation in management account [#406](https://github.com/noqdev/iambic/pull/406)
* `datfinesoul` for reporting AWS change detection setup issue [#407](https://github.com/noqdev/iambic/pull/407)
* `mxw-sec` for reviewing [#420](https://github.com/noqdev/iambic/pull/420)
* `sprkyco` for reporting directory extension Azure AD issue [#423](https://github.com/noqdev/iambic/pull/423)

## 0.7.6 (May 15th, 2023)

BUG FIXES:

* Handling merge models when the new value is an int
* Flatten multiline comment when they are not attached to a YAML dict key

ENHANCEMENTS:
* Added an `iambic convert` command to convert an AWS policy to the IAMbic formatted yaml
* Default relative directory leverages `path` information from IAM resources. [#400](https://github.com/noqdev/iambic/pull/400)

THANKS:

* `Shreyas D` for reporting the merge model issue
* `Phil H, Michael W` for suggesting the `iambic convert` command

## 0.7.3 (May 10th, 2023)

BUG FIXES:

* AWS plugin now supports legacy policy document schema. (This is an undocumented
schema in which statement can be a single statement not wrapped inside an array.
New policy editor will always use the array syntax; however, there are old policies
that have the legacy syntax. IAMbic should handle it gracefully without crashing.)

THANKS:

* `Shreyas D` reported the issue [#397](https://github.com/noqdev/iambic/pull/397)


## 0.7.1 (May 9th, 2023)

ENHANCEMENTS:

* Tag support on CloudFormation stack. These tags will propagate to IambicHubRole and
IambicSpokeRole created. Wizard will prompt the user to either enter blank or
in `key1=value1` format. To add multiple tags, use `key1=value1, key2=value2` format.

BUG FIXES:

* Fixes in wizard when user does not grant Iambic write access.
* Fixes in wizard when setting up an individual AWS account instead of AWS Organization.

THANKS:

* `Phil H.`, `David B.` in [NoqCommunity](https://noqcommunity.slack.com/archives/C02P9E8BDK6/p1683275443604049) proposing tags support during IAMbic setup.

## 0.6.1 (May 3rd, 2023)

ENHANCEMENTS:

* Additional clarity in the wizard as it relates to AWS cloudformation changes.
* Added the ability to check the IAMbic version from the CLI.

BUG FIXES:

* AWS read only spoke role is now working as designed
* Fixes to text being truncated in the wizard on smaller terminal windows.

THANKS:

* [rjulian](https://github.com/rjulian) for reporting [#377](https://github.com/noqdev/iambic/pull/377).

## 0.5.1 (May 2nd, 2023)

PERMISSION CHANGES:

* IambicHubRole now uses a region agnostic resource definition in the SQS `IAMbicChangeDetectionQueue` permission (CloudFormation Template)

ENHANCEMENTS:

* The AWS region IAMbic uses is now configurable in the wizard.
* Added region awareness to cloud formation util functions.

BREAKING CHANGES:

* The `AwsIdentityCenterPermissionSetTemplate` schema has changed. In particular, `permissions_boundary.policy_arn` has become `permissions_boundary.managed_policy_arn`. This is due to the PermissionSet API distinguishing attached
permissions_boundary either owned by AWS or owned by Customer. To align with AWS API response, we have decided
to follow the AWS naming convention. The old name `permissions_boundary.policy_arn` never quite worked correctly
in `AwsIdentityCenterPermissionSetTemplate`. We decide to go through with the breaking change route.

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
