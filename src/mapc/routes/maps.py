from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response
from PIL import Image, UnidentifiedImageError
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from mapc.db import SessionDep
from mapc.models.camera import Camera, CameraPlacement
from mapc.models.map import Map
from mapc.schemas.map import MapResponse, PlacementInput, PlacementResponse

router = APIRouter(prefix="/maps", tags=["Maps"])
# Maps are stored at their original resolution without a pixel limit.
Image.MAX_IMAGE_PIXELS = None


def image_info(data: bytes) -> tuple[str, int, int]:
    try:
        with Image.open(BytesIO(data), formats=["PNG", "JPEG"]) as image:
            width, height = image.size
            if getattr(image, "n_frames", 1) != 1:
                raise HTTPException(415, "Animated images are not supported")
            if image.getexif().get(274, 1) != 1:
                raise HTTPException(
                    415, "Save the image without EXIF rotation before uploading"
                )
            mime = "image/png" if image.format == "PNG" else "image/jpeg"
        # Reading PNG EXIF may load the image; verify needs a freshly opened file.
        with Image.open(BytesIO(data), formats=["PNG", "JPEG"]) as image:
            image.verify()
        with Image.open(BytesIO(data), formats=["PNG", "JPEG"]) as image:
            image.load()
        return mime, width, height
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise HTTPException(415, "A valid PNG or JPEG image is required") from None


def save_map(engine, name: str, data: bytes) -> MapResponse:
    mime, width, height = image_info(data)
    with Session(engine) as db:
        item = Map(name=name, image=data, mime_type=mime, width=width, height=height)
        db.add(item)
        db.commit()
        db.refresh(item)
        return MapResponse.model_validate(item)


@router.post("/", response_model=MapResponse, status_code=201)
async def upload_map(
    request: Request, name: Annotated[str, Query(min_length=1, max_length=200)]
):
    """Body: raw PNG/JPEG bytes (not JSON, Base64 or multipart)."""
    name = name.strip()
    if not name:
        raise HTTPException(422, "Map name must not be empty")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
    return await run_in_threadpool(
        save_map, request.app.state.engine, name, bytes(data)
    )


@router.get("/", response_model=list[MapResponse])
def list_maps(db: SessionDep):
    # Do not load image BLOBs when listing metadata.
    rows = db.exec(select(Map.id, Map.name, Map.mime_type, Map.width, Map.height)).all()
    return [dict(row._mapping) for row in rows]


@router.get("/{map_id}", response_model=MapResponse)
def get_map(map_id: int, db: SessionDep):
    row = db.exec(
        select(Map.id, Map.name, Map.mime_type, Map.width, Map.height).where(
            Map.id == map_id
        )
    ).first()
    if row is None:
        raise HTTPException(404, "Map not found")
    return dict(row._mapping)


@router.get("/{map_id}/image")
def get_image(map_id: int, db: SessionDep):
    item = db.get(Map, map_id)
    if item is None:
        raise HTTPException(404, "Map not found")
    return Response(
        item.image,
        media_type=item.mime_type,
        headers={"X-Content-Type-Options": "nosniff"},
    )


def require_map(map_id: int, db: Session):
    if db.exec(select(Map.id).where(Map.id == map_id)).first() is None:
        raise HTTPException(404, "Map not found")


@router.get("/{map_id}/placements", response_model=list[PlacementResponse])
def list_placements(map_id: int, db: SessionDep):
    require_map(map_id, db)
    return db.exec(
        select(CameraPlacement).where(CameraPlacement.map_id == map_id)
    ).all()


@router.put("/{map_id}/placements/{camera_id}", response_model=PlacementResponse)
def put_placement(map_id: int, camera_id: int, data: PlacementInput, db: SessionDep):
    require_map(map_id, db)
    if db.get(Camera, camera_id) is None:
        raise HTTPException(404, "Camera not found")
    item = db.exec(
        select(CameraPlacement).where(
            CameraPlacement.map_id == map_id, CameraPlacement.camera_id == camera_id
        )
    ).first()
    if item is None:
        item = CameraPlacement(map_id=map_id, camera_id=camera_id, **data.model_dump())
    else:
        for key, value in data.model_dump().items():
            setattr(item, key, value)
    db.add(item)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409, "Another request changed this placement. Try saving again."
        ) from None
    db.refresh(item)
    return item


@router.delete("/{map_id}/placements/{camera_id}", status_code=204)
def delete_placement(map_id: int, camera_id: int, db: SessionDep):
    require_map(map_id, db)
    item = db.exec(
        select(CameraPlacement).where(
            CameraPlacement.map_id == map_id, CameraPlacement.camera_id == camera_id
        )
    ).first()
    if item is None:
        raise HTTPException(404, "Placement not found")
    db.delete(item)
    db.commit()
    return Response(status_code=204)
