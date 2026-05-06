from pydantic import BaseModel


class DeleteAccountRequest(BaseModel):
    password: str | None = None
    confirm_text: str


class MessageResponse(BaseModel):
    message: str


class UserProfileResponse(BaseModel):
    id: str
    is_deleted: bool
    has_telegram: bool
    has_web_account: bool