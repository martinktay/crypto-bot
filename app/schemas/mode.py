from pydantic import BaseModel

from app.core.enums import ApprovalMode


class ModeUpdateRequest(BaseModel):
    approval_mode: ApprovalMode | None = None
