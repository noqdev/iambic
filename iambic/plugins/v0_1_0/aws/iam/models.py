from __future__ import annotations

from iambic.plugins.v0_1_0.aws.models import AccessModel


class Path(AccessModel):
    file_path: str

    @property
    def resource_type(self) -> str:
        return "iam:path"

    @property
    def resource_id(self) -> str:
        return self.file_path


class MaxSessionDuration(AccessModel):
    max_session_duration: int

    @property
    def resource_type(self) -> str:
        return "iam:max_session_duration"

    @property
    def resource_id(self) -> str:
        return str(self.max_session_duration)
