from sqlmodel import Field, SQLModel


class Map(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    image: bytes = Field(repr=False)
    mime_type: str
    width: int
    height: int
