from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Index, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from mapc.models.stream import Stream


class Camera(SQLModel, table=True):
    __tablename__ = "cameras"
    __table_args__ = (
        Index("uq_camera_endpoint", "ip", "port", "protocol", unique=True),
    )

    id: int | None = Field(default=None, primary_key=True)
    ip: str = Field(index=True)
    port: int
    protocol: str
    manufacturer: str
    model: str
    firmware: str
    serial_number: str
    mac_address: str
    created: datetime = Field(default_factory=datetime.now)
    updated: datetime = Field(default_factory=datetime.now)
    is_active: bool = Field(default=False)
    streams: list["Stream"] = Relationship(back_populates="camera")


class CameraPlacement(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("map_id", "camera_id"),
        CheckConstraint("x >= 0 AND x <= 1 AND y >= 0 AND y <= 1"),
        CheckConstraint("direction >= 0 AND direction < 360"),
        CheckConstraint("view_angle > 0 AND view_angle <= 360"),
        CheckConstraint("view_distance > 0 AND view_distance <= 2"),
    )
    id: int | None = Field(default=None, primary_key=True)
    map_id: int = Field(foreign_key="map.id", index=True)
    camera_id: int = Field(foreign_key="cameras.id", index=True)

    x: float
    y: float
    direction: float = 0
    view_angle: float = 90
    view_distance: float = 0.1
