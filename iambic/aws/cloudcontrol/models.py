from iambic.aws.models import AccessModel, AWSTemplate


# How do I have a base template and modify it with all of the supported types?
class CloudControlBase():
    
    
type('NewClass', (CloudControlBase, AWSTemplate, AccessModel), {})