from typing import Union


class ExecutionContext:
    eval_only: bool = False

    iambic_managed_preference: Union[bool, None] = None

    @property
    def execute(self):
        return not self.eval_only


ctx = ExecutionContext()
