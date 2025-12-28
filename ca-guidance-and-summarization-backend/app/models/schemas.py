from pydantic import BaseModel
from typing import Optional

class UserInfo(BaseModel):
    email: str
    name: str
    picture: Optional[str] = None
    access_token: Optional[str] = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo

class SummarizeRequest(BaseModel):
    topic: str

