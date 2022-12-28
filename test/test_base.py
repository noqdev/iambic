from __future__ import annotations

from unittest import TestCase


class TemplateBaseTestCase(TestCase):
    """
    This class helps to clearly define expectations for testing an iambic template.
    It defines the methods for providing the minimum set of expected tests for contribution.
    If any test does not apply to the template being tested, simply override the method with "pass"
    """

    def create_base_resource(self):
        """
        Create the bare minimum resource.
        Check that it was created and the object values are all correctly set on the provider.

        Example:
            Create a basic AWS IAM Role
                Verify the role is now there
                Check that the tags, name, description, and assume role policy document are correct
        """
        raise NotImplementedError

    def base_resource_invalid_value(self):
        """
        Check how a non-standard response from the provider is handled after an invalid value is provided.
        """
        raise NotImplementedError

    def create_complex_resource(self):
        """
        If the template represents multiple resources for the provider
        use this to test if not only the primary resource is created but its related resources.

        Example:
            Create an AWS IAM Role with inline policies, tags, and managed policies (managed policy ref)
                These are only attached to a single role but are technically different resources.
                They are updated, deleted, and for some created via entirely different API calls.
                Verify the role is there and correct
                Verify each related resource was also created correctly
        """
        raise NotImplementedError

    def create_resource_multi_account_values(self):
        """
        If this template can be applied to multiple accounts on the provider
        use this to test a scenario where a value is different between accounts.

        Example:
            Create an AWS IAM Role in 2 accounts.
            Account 1 has a description of "I am for testing"
            Account 2 has a description of "I am for validating"
            Check the description is set correctly for both accounts.
        """
        raise NotImplementedError

    def update_base_resource(self):
        """
        Create a bare minimum resource and attempt to update one or more attributes.

        Example:
            Create an AWS IAM Role in 2 accounts.
            Account 1 has a description of "I am for testing"
            Account 2 has a description of "I am for validating"
            Check the description is set correctly for both accounts.
        """
        raise NotImplementedError

    def update_complex_resource(self):
        """
        If the template represents multiple resources for the provider
        use this to test if not only the primary resource is updated but its related resources.

        Example:
            Create an AWS IAM Role with inline policies, tags, and managed policies (managed policy ref)
            Update the 1 or more attribute of each related resource
                Verify each related resource was update correctly
        """
        raise NotImplementedError

    def delete_base_resource(self):
        """
        Create a bare minimum resource then attempt to delete it.

        Example:
            Create an AWS IAM Role.
            Attempt to delete it.
            Confirm the role was deleted.
        """
        raise NotImplementedError

    def delete_multi_account_resource(self):
        """
        If this template can be applied to multiple accounts on the provider
        use this to test a scenario where the resource was deleted across all accounts.

        Example:
            Create an AWS IAM Role in 2 accounts.
            Attempt to delete them.
            Confirm the role was deleted on both accounts.
        """
        raise NotImplementedError

    def delete_complex_resource(self):
        """
        If the template represents multiple resources for the provider
        use this to test if not only the primary resource is deleted but its related resources.

        Example:
            Create an AWS IAM Role with inline policies, tags, and managed policies (managed policy ref)
            Delete the role.
            Verify not only the role was deleted but all resources related to it.
        """
        raise NotImplementedError
