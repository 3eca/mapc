from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from mapc.db import SessionDep
from mapc.models.camera import Camera, CameraPlacement
from mapc.models.stream import Stream
from mapc.schemas.camera import CameraCreate, CameraResponse
from mapc.services.snapshot import SnapshotError

router = APIRouter(prefix="/camera", tags=["Camera"])


@router.get("/", response_model=list[CameraResponse], status_code=status.HTTP_200_OK)
def get_cams(db: SessionDep) -> list[Camera]:
    return list(db.exec(select(Camera)).all())


@router.post("/", response_model=CameraResponse, status_code=status.HTTP_201_CREATED)
def add_cam(cam: CameraCreate, db: SessionDep) -> Camera:
    exists = db.exec(
        select(Camera).where(
            Camera.ip == cam.ip,
            Camera.port == cam.port,
            Camera.protocol == cam.protocol,
        )
    ).first()
    if exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Camera exists: {exists.ip}:{exists.port}",
        )
    c = Camera(
        ip=cam.ip,
        port=cam.port,
        protocol=cam.protocol,
        manufacturer=cam.manufacturer,
        model=cam.model,
        firmware=cam.firmware,
        serial_number=cam.serial_number,
        mac_address=cam.mac_address,
        is_active=True,
        streams=[Stream(**stream.model_dump()) for stream in cam.streams],
    )
    db.add(c)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        exists = db.exec(
            select(Camera).where(
                Camera.ip == cam.ip,
                Camera.port == cam.port,
                Camera.protocol == cam.protocol,
            )
        ).first()
        if exists:
            raise HTTPException(409, "Camera already exists in the database") from None
        raise
    db.refresh(c)
    return c


@router.get("/{camera_id}/snapshot")
async def camera_snapshot(camera_id: int, request: Request, db: SessionDep):
    camera = db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(404, "Camera not found")
    if camera.protocol != "onvif":
        raise HTTPException(409, "Add the camera through ONVIF to request snapshots")
    try:
        data, mime = await request.app.state.snapshots.get(
            camera.id, camera.ip, camera.port
        )
    except SnapshotError as error:
        raise HTTPException(
            502, str(error), headers={"Cache-Control": "no-store"}
        ) from None
    return Response(
        data,
        media_type=mime,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_camera(camera_id: int, db: SessionDep):
    if db.get(Camera, camera_id) is None:
        raise HTTPException(404, "Camera not found")
    db.exec(delete(CameraPlacement).where(CameraPlacement.camera_id == camera_id))
    db.exec(delete(Stream).where(Stream.camera_id == camera_id))
    db.exec(delete(Camera).where(Camera.id == camera_id))
    db.commit()
    return Response(status_code=204)
