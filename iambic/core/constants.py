# When do you use this constant?
# Typically the read_only attribute is part of the model,
# you will access the attribute instance. It only makes
# sense if you are using "reflect" like techniques to
# examine a borad class of instance.
#
# TODO: should we discuss how to manage concept that
# should be supported across all types of resources.
# Currently, everyone supported cloud resources type
# have to have its own implementation of read_only
READ_ONLY_TOKEN = "read_only"
