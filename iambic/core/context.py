from __future__ import annotations


class ExecutionContext:
    eval_only: bool = False

    @property
    def execute(self):
        return not self.eval_only


ctx = ExecutionContext()
