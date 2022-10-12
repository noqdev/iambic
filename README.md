# noqform
The python package used to generate, parse, and execute noqform yaml templates.

# Template Generation

## How to run
`python -m noq_form.main generate -c demo/config.yaml`

## How it works

### `group_str_attribute(account_configs: list[AccountConfig], account_resources: list[dict]) -> Union[str | dict[str, list]]`
Groups a string attribute by a shared name across of accounts.
The ability to pass in and maintain arbitrary keys is necessary for parsing resource names related to a boto3 response.
An example of this would be roles and maintaining the reference to the role's file path. 

:param account_configs: list[AccountConfig]
:param account_resources: list[dict(account_id:str, resources=list[dict(resource_val: str, **)])]
:return: dict(attribute_val: str = list[dict(resource_val: str, account_id: str, **)])

It works by creating a map of the 2 different representations of the string. 
That is the raw string and the string with jinja compatible variables added.
An example of this would be `prod_admin_role` vs `{{account_name}}_admin_role`.

Another map is then created where the key is the index position of the original value in `resources` and the value is the different representations of the string.

A nested for-loop then checks for string matches across accounts. This is used to form the response.
When there's a hit the reference maps created earlier are nulled out.

A final for loop creates the one-off resource values (`resource_val`). 
These are values only observed in 1 account. It works by looking for references that are not None.
If multiple representations of the value are observed (`prod_admin_role` vs `{{account_name}}_admin_role`) the raw string is used `prod_admin_role`.


### group_dict_attribute(account_configs: list[AccountConfig], account_resources: list[dict]):
Groups an attribute that is a dict or list of dicts by with matching accounts

:param account_configs: list[AccountConfig]
:param account_resources: list[dict(account_id:str, resources=list[dict])]
:return: list[dict(included_accounts: str, resource_val=list[dict]|dict)]

The way `group_dict_attribute` works is very similar to `group_str_attribute`.
The primary distinction is, instead of using the resource values a hashed reference to the value is used.

The reason the `resource_val` key exists is due to the fact the value can be a list or dict.
It is the responsibility of the caller to format the response as needed.

### Role Templates

The function responsible for generating role templates is:
`aws.iam.role.template_generation.generate_aws_role_templates`

It can be broken down into several steps
1. Gathering all the account configs across all provided configs
2. Retrieving all roles for each account and writing them to disk in a semaphore. 
3. Pull all inline policies for all roles and update the files created in step 2. This is done in a semaphore.
4. Pull all managed policies for all roles and update the files created in step 2. This is done in a semaphore.
5. Group the roles by their name
6. Group each attribute for each grouped role
7. Normalize the grouped attributes to a MultiAccountRoleTemplate instance
8. Write the instance to `pathlib.Path.cwd().joinpath("resources", "aws", "roles")`


#### Design Decisions
Why write to disk?
So we don't have to hold everything in memory which could get rough for tenants with hundreds of accounts. Instead, we keep a small ref to the role.

#### TODO
Creating the template has been done* but haven't verified the templates are valid
General clean up for the currently messy nature of `group_str_attributes`
Extracting `role_access` from `tags` in the response
The following attributes aren't really functional:
* path - Only works if value is the same for all accounts
* description - Only works if value is the same for all accounts
* managed_policy - Not fully hooked up
* tags - Not fully hooked up
* role_access - Not started
* permissions_boundary - Not started

