from iambic.output.markdown import render_resource_changes

def test_render_resource_changes():
    resource_changes = [
        {'resource_type': 'EC2 Instance', 'resource_id': 'i-1234567890abcdefg', 'action': 'Stop', 'proposed_change': 'None', 'accounts': ['Account A', 'Account B'], 'template_id': 'template_1'},
        {'resource_type': 'RDS Instance', 'resource_id': 'db-abcdefghijklmno', 'action': 'Delete', 'proposed_change': 'None', 'accounts': ['Account A'], 'template_id': 'template_1'},
        {'resource_type': 'Lambda Function', 'resource_id': 'arn:aws:lambda:us-west-2:123456789012:function:my-function', 'action': 'Update', 'proposed_change': 'Increase Memory', 'accounts': ['Account B'], 'template_id': 'template_2'},
        {'resource_type': 'S3 Bucket', 'resource_id': 'my-bucket', 'action': 'Delete', 'proposed_change': 'None', 'accounts': ['Account A', 'Account B'], 'template_id': 'template_2'},
    ]

    expected_output = '''
<table>
    <thead>
        <tr>
            <th>Template ID</th>
            <th>Account</th>
            <th>Resource Type</th>
            <th>Resource ID</th>
            <th>Action</th>
            <th>Proposed Change</th>
        </tr>
    </thead>
    <tbody>
        <tr class="accordion-toggle">
            <td rowspan="1">template_1</td>
            <td>Account A</td>
            <td>RDS Instance</td>
            <td>db-abcdefghijklmno</td>
            <td>Delete</td>
            <td>None</td>
        </tr>
            <tr class="accordion-toggle">
            <td rowspan="1">template_1</td>
            <td>Account A, Account B</td>
            <td>EC2 Instance</td>
            <td>i-1234567890abcdefg</td>
            <td>Stop</td>
            <td>None</td>
        </tr>
            <tr class="accordion-toggle">
            <td rowspan="1">template_2</td>
            <td>Account A, Account B</td>
            <td>S3 Bucket</td>
            <td>my-bucket</td>
            <td>Delete</td>
            <td>None</td>
        </tr>
            <tr class="accordion-toggle">
            <td rowspan="1">template_2</td>
            <td>Account B</td>
            <td>Lambda Function</td>
            <td>arn:aws:lambda:us-west-2:123456789012:function:my-function</td>
            <td>Update</td>
            <td>Increase Memory</td>
        </tr>
            </tbody>
</table>
'''

    # Render the actual output
    actual_output = render_resource_changes(resource_changes)

    with open("test.md", "w") as f:
        f.write(actual_output)

    # Compare the expected and actual output
    assert actual_output.strip().replace(' ', '') == expected_output.strip().replace(' ', '')
