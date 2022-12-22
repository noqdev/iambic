# SSO Design Decisions


## SSO Permission Set
If you've seen how permission sets are implemented you're probably wondering why. Here's the answer.


### IAMbic design
Due to limitations with the AWS API (see below for more details) permission sets are handled differently than other resources. 

After the full list of templates have been collected and all aws accounts have been set in the config generate_permission_set_map is called.

This function generate a map of permission sets for AWS accounts that are referenced in at least 1 template.
This map is set as an attribute under the account instance `AWSAccount.sso_details.permission_set_map`.

That attribute is then referenced when updating or removing an existing permission set.
We add the `generate_permission_set_map` function, so we can set the attribute lazily and reduce unnecessary calls to AWS.


### AWS API Limitation
While the name of a permission set is unique to the org it is not used by the AWS API for any operation.
All operations require the permission set ARN and instance ARN. 

The problem with the permission set ARN is that it is simply a random alphanumeric string.
As a result we have no way to templatize the attribute AWS SSO uses to identify the permission set.
An example permission set arn: `arn:aws:sso:::permissionSet/ssoins-0000e000c6a1baec/ps-1f9999f9999999b3`.


### Decision
We could capture it in the template as an immutable attribute but the UX would be terrible.

It would be okay-ish on import but to create a new permission set you would have to either:
* Create it in the AWS console and remove the ability to create a permission set in IAMbic
* Create it, run a follow-up command to import the ARN, create a new PR to update the template, and merge it

So, instead we eat the cost to generate a map on the fly when a permission set template is modified.
It's a better UX but the flow is a little backwards.

Basically, we're treating org as an attribute of the account it is on, which it is; instead of treating an org as way to manage a series of accounts (which it also is). 

