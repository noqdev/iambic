# Contribution Doc


## Writing new templates or models

Each attribute should support a single value or multiple values on the boundary of accounts.
An example of this would be `Role.path`. Notice how path can be a str or list of `Path` instances.
```python
class Path(AccessModel):
    file_path: str


class RoleTemplate(NoqTemplate, AccessModel):
    ...
    path: Optional[Union[str | list[Path]]] = "/"
```

NEVER use dict to represent an attribute unless absolutely necessary due to the attributes dynamic nature.
An example of this would be `PolicyStatement.condition` where key is the condition statement making representing the attribute too difficult. 
 

## Adding a new resource model
This section is applies to any type of model class include `NoqTemplate` classes. 

### Implement `resource_type(self) -> str:`
A unique representation of the resource's type. 
For AWS resources this would be `aws:${service}:${resource}` e.g. aws:iam:role.
There is no strict standard at the time this was written so use your best judgement.
Be sure that it is named in such a way that no model in iambic will ever collide.

### Implement `resource_id(self) -> str:`
The unique value for the resource.  
For a role this would be the role name. For a tag it would be the key. For an inline policy, the policy name.

### Optionally overwrite `exclude_keys(self) -> set` 
Used to specify attributes in a model that are not part of the API request to the related service e.g. AWS/boto3.

This method only extends the following set of attributes which are already ignored:
```python
exclude_keys = {
    "deleted",
    "expires_at",
    "included_accounts",
    "excluded_accounts",
    "included_orgs",
    "excluded_orgs",
    "owner",
    "template_type",
    "file_path",
}
```

## Adding a new Noq template
A Noq template defines 1 or more resources. 
A template will typically only have 1 resource attributed to it. 
For example, a template that defines a managed policy.
This managed policy will be applied to the accounts defined by included/exclude accounts and included/excluded orgs.

However, resources that have a 1-1 or 1-N relationship with another resource will also include those resources in its template.
For example, a role has tags and those tags cannot be attributed to any other resource making them bound to the role.
Therefore, the tags are defined as an attribute of the role. The same applies to inline policies and assume role policies.
Managed policies can be attached to many roles so the managed policy is not an attribute of the role template.

Below are some other guidelines for defining a template class and incorporating a new template into iambic.

### Define `template_type`
This is the string value used to identify a template's type.
The value is unique across all NoqTemplate classes in iambic.
This value MUST be prefixed with `NOQ::`.

### Implement `async def _apply_to_account(self, account_config: AccountConfig) -> bool:`  
This method is responsible for conditionally updating, creating, or deleting the resources the template represents.
For example, the AWS role template also carries with it tag resources, inline policy resources, instances profiles, etc.
This method will not only upsert or delete the role but also these related resources. 

### Add the class to `iambic.config.templates.TEMPLATES`
This list is used for validation and resolving the template type of a yaml file.

### Create an async function to import existing resources
* Add the function to a module called `template_generation.py` that will be in the same package as the template's model.
* Must group resources with identical `resource_id`
* Must group attributes of the resource
* Take into account the jinja representation and the raw value when grouping
* Check if resource is already a template and overwrite that file before creating a new file
* Follow the iambic preferred directory structure of `resources/${provider}/${resource}` e.g. resources/aws/roles
* Add the function to import existing resources to `iambic.request_handler.generate.generate_templates`

#### Use the helper functions
There are a number of functions in `iambic.core.template_generation.py` to simplify a lot of the import process. 

##### `group_int_or_str_attribute(account_config_map: dict[str, AccountConfig], number_of_accounts_resource_on: int, account_resources: Union[dict | list[dict]], key: Union[int | str]) -> Union[int | str | list[dict]]:`
Groups an attribute by accounts, formats the attribute and normalizes the included accounts.

:param account_config_map:
:param number_of_accounts_resource_on:
:param account_resources: list[dict(account_id:str, resources=list[dict])]
:param is_dict_attr: If false and only one hit, still return as a list. Useful for things like inline_policies.

##### `group_dict_attribute(account_config_map: dict[str, AccountConfig], number_of_accounts_resource_on: int, account_resources: list[dict], is_dict_attr: bool = True) -> Union[dict | list[dict]]:`
Groups an attribute by accounts, formats the attribute and normalizes the included accounts.

:param account_config_map: {account_id: account_config}
:param number_of_accounts_resource_on:
:param account_resources: list[dict(account_id:str, resources=list[dict])]
:param is_dict_attr: If false and only one hit, still return as a list. Useful for things like inline_policies.
:return:

##### `base_group_dict_attribute(account_config_map: dict[str, AccountConfig], account_resources: list[dict]) -> list[dict]:`
Groups an attribute that is a dict or list of dicts with matching accounts

Call group_dict_attribute instead unless you need to transform this response.
An example would be tags which also contain role_access.

:param account_config_map: dict(account_id:str = AccountConfig)
:param account_resources: list[dict(account_id:str, resources=list[dict])]
:return: list[dict(included_accounts: str, resource_val=list[dict]|dict)]

##### `base_group_str_attribute(account_config_map: dict[str, AccountConfig], account_resources: list[dict]) -> dict[str, list]:`
Groups a string attribute by a shared name across of accounts

The ability to pass in and maintain arbitrary keys is necessary for parsing resource names related to a boto3 response.
It's also useful when the str is a reference object like inline policies where the str is a policy name.

Call group_int_or_str_attribute instead unless you need to transform this response.
An example would be grouping role names for generating the template where you need to keep the file_path ref.

:param account_config_map: dict(account_id:str = AccountConfig)
:param account_resources: list[dict(account_id:str, resources=list[dict(resource_val: str, **)])]
:return: dict(attribute_val: str = list[dict(resource_val: str, account_id: str, **)])

##### `set_included_accounts_for_grouped_attribute(account_config_map: dict[str, AccountConfig], number_of_accounts_resource_on: int, grouped_attribute) -> Union[list | dict]:`
Takes a grouped attribute and formats its `included_accounts` to * or a list of account names

:param account_config_map: {account_id: account_config}
:param number_of_accounts_resource_on:
:param grouped_attribute:
:return:

#### Use `iambic.aws.iam.role.template_generation.generate_aws_role_templates` as an example
While `generate_aws_role_templates` is somewhat complex what it's doing can be broken out into a series of steps that can be used for any other template type.

1. Retrieve the primary resource and write it into a file and create a map where {resource_id: file_path}
2. Retrieve related resources and update the file created in step 1
3. Format the resource file map to the structure expected by `base_group_str_attribute`
4. Now that the resources have been grouped by their id group the attributes for the resource across accounts and write the template. 
   1. Use `create_templated_role` as an example. The way it works should translate for any other template.

## Testing

TODO