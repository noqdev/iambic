from __future__ import annotations

from iambic.core.iambic_enum import Command


class ExecutionContext:
    eval_only: bool = False
    use_remote: bool = False
    command: Command = None

    @property
    def execute(self):
        return not self.eval_only


ctx = ExecutionContext()
