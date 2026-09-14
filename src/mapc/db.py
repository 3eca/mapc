from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.engine import Engine, make_url
from sqlmodel import Session, SQLModel, create_engine

from mapc.settings import AppSettings


def build_engine(settings: AppSettings) -> Engine:
    url = make_url(settings.database_url)
    if (
        url.get_backend_name() == "sqlite"
        and url.database not in {None, "", ":memory:"}
        and url.query.get("uri") != "true"
    ):
        path = Path(url.database)
        if path.is_dir():
            raise ValueError(
                f"SQLite database path is a directory: {path}. "
                "Mount its parent directory instead of the database file."
            )
        path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(url)


def init_db(engine: Engine) -> None:
    # Import models explicitly so initialization also works outside the app module.
    from mapc.models.camera import Camera
    from mapc.models.map import Map  # noqa: F401
    from mapc.models.stream import Stream  # noqa: F401

    SQLModel.metadata.create_all(engine)
    # create_all does not add indexes to existing tables.
    for index in Camera.__table__.indexes:
        if index.name == "uq_camera_endpoint":
            index.create(engine, checkfirst=True)


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
