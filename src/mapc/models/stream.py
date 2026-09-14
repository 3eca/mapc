from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from mapc.models.camera import Camera


class Stream(SQLModel, table=True):
    __tablename__ = "streams"

    id: int | None = Field(default=None, primary_key=True)
    camera_id: int = Field(foreign_key="cameras.id", index=True)

    profile: str
    token: str
    uri: str = Field(repr=False)
    camera: "Camera" = Relationship(back_populates="streams")
