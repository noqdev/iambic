# SSO Design Decisions


## SSO Permission Set
If you've seen how permission sets are implemented you're probably wondering why. Here's the answer.


### IAMbic design
Due to limitations with the AWS API (see below for more details) permission sets are handled differently than other resources. 

After the full list of templates have been collected and all aws accounts have been set in the config `AWSAccount.sso_details.set_sso_details` is called.

This method generates various maps used that are required for interfacing with permission sets.
This includes a map of the permission sets, the SSO users, the SSO groups, and the org accounts.

For example, the permission set map is an attribute under the account instance `AWSAccount.sso_details.permission_set_map`.
That attribute is referenced when updating or removing an existing permission set.
There is also a method `AWSAccount.sso_details.set_sso_details` that is called lazily when a permission set template is being used.


### Why are SSO resources referenced as part of the account the org is in instead of the actual org in app code?

IAMbic is designed so that every AWS resource belongs to an account.  
Think of SSO resources almost like a sub-resource. 
They belong to an org which is a resource on an account.

Otherwise, we'd need to have to different flows for AWS resources (one for org and one for account) depending on the resource type.

TLDR; we're treating org as an attribute of the account it is on, which it is; instead of treating an org as way to manage a series of accounts (which it also is). 


### AWS API Limitation
While the name of a permission set is unique to the org it is not used by the AWS API for any operation.
All operations require the permission set ARN and instance ARN. 

The problem with the permission set ARN is that it is simply a random alphanumeric string.
As a result we have no way to templatize the attribute AWS SSO uses to identify the permission set.
An example permission set arn: `arn:aws:sso:::permissionSet/ssoins-0000e000c6a1baec/ps-1f9999f9999999b3`.

We could capture it in the template as a static, auto-generated attribute but the UX would be terrible.

It would be okay-ish on import but to create a new permission set you would have to either:
* Create it in the AWS console and remove the ability to create a permission set in IAMbic
* Create it, run a follow-up command to import the ARN, create a new PR to update the template, and merge it

So, instead we eat the cost to generate a map on the fly when a permission set template is modified.
It's a better UX but the flow is a little backwards.

### Performance considerations
SSO resource templates are going to take more time to process than other resources.
For reasons I can't explain, per AWS' documentation: 
"IAM Identity Center APIs have a collective throttle maximum of 20 transactions per second (TPS). 
The CreateAccountAssignment has a maximum rate of 10 outstanding async calls. 
These quotas cannot be changed."

As a result we will likely have to process SSO resources templates synchronously to avoid throttling.

### Access Rules vs Account Assignments
It may seem as though the 2 terms are used interchangeably but they're really 2 different ways to represent the same concept.
They are both a way to associate a user or group with a permission set on an account in AWS.

An account assignment is an AWS SSO concept where each assignment represents a single combination.
For example, the group engineering@noq.dev being assigned access to the engineering permission set on the noq-dev account.

On the other hand, an access rule is a concept used by IAMbic.
Access rules are more expressive as you can assign multiple users or groups to a permission set on multiple accounts via a list regexes.
Under the hood, an access rule equates to a list of account assignments.
There was an effort to change the naming of variables on an access rule when it is translated to an account assignment.


### What about Account Rules in the config? Are they evaluated for my SSO account definition?
Long story short, they're not evaluated for SSO resource templates.

Why?
This is a complicated topic but ultimately it boils down to how permission sets work under the hood in AWS.
When you create a permission set in AWS that permission set is assigned to a user or group in the org accounts.
While the role is created on the assigned account, the permission set and account assignments actually exist on and are managed by the SSO account.
Also, when a permission set template is defined it is in the scope of the SSO account, not the assigned accounts.
So, it was decided that account rules should not be evaluated for SSO account definitions.

