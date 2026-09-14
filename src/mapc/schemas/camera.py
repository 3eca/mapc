from datetime import datetime

from pydantic import BaseModel
from sqlmodel import Field

from mapc.schemas.stream import StreamCreate


class CameraResponse(BaseModel):
    id: int | None
    ip: str
    port: int
    protocol: str
    manufacturer: str
    model: str
    firmware: str
    serial_number: str
    mac_address: str
    created: datetime
    updated: datetime
    is_active: bool
    streams: list["StreamCreate"]


class CameraCreate(BaseModel):
    ip: str
    port: int
    protocol: str
    manufacturer: str
    model: str
    firmware: str
    serial_number: str
    mac_address: str
    is_active: bool = True
    streams: list["StreamCreate"] = Field(default_factory=list)
