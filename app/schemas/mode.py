from pydantic import BaseModel

from app.core.enums import TradingMode


class ModeUpdateRequest(BaseModel):
    mode: TradingMode
