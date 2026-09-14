from pydantic import BaseModel


class StreamCreate(BaseModel):
    profile: str
    token: str
    uri: str
