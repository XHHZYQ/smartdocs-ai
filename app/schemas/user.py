from pydantic import EmailStr
from sqlmodel import SQLModel


class UserCreate(SQLModel):
    email: EmailStr
    password: str


class UserRead(SQLModel):
    id: int
    email: str


class Token(SQLModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessTokenResponse(SQLModel):
    access_token: str
    token_type: str = "bearer"


class RefreshRequest(SQLModel):
    refresh_token: str