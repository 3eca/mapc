from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from sqlmodel import select

from mapc.db import SessionDep
from mapc.models.camera import Camera
from mapc.routes.cameras import add_cam
from mapc.schemas.camera import CameraCreate
from mapc.services.scan_manager import ScanError, ScanManager

router = APIRouter(prefix="/scans", tags=["Scanner"])


@router.post("/", status_code=status.HTTP_202_ACCEPTED)
async def start_scan(request: Request) -> dict[str, Any]:
    manager: ScanManager = request.app.state.scan_manager

    try:
        return manager.start()
    except ScanError as er:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(er)
        ) from er


@router.get("/{scan_id}")
def get_scan(scan_id: str, request: Request, db: SessionDep):
    manager: ScanManager = request.app.state.scan_manager

    try:
        job = manager.get(scan_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scan not found",
        ) from None

    if job["result"] is not None:
        existing = {
            (ip, port, protocol): camera_id
            for camera_id, ip, port, protocol in db.exec(
                select(Camera.id, Camera.ip, Camera.port, Camera.protocol)
            ).all()
        }
        for categories in job["result"].values():
            for cameras in categories.values():
                for camera in cameras:
                    camera_id = existing.get(
                        (camera["ip"], camera["port"], camera["protocol"])
                    )
                    camera["already_exists"] = camera_id is not None
                    camera["camera_id"] = camera_id

    return job


@router.post("/{scan_id}/cameras/{camera_index}", status_code=status.HTTP_201_CREATED)
def save_scanned_camera(
    scan_id: str, camera_index: int, request: Request, db: SessionDep
):
    manager: ScanManager = request.app.state.scan_manager
    try:
        job = manager.get(scan_id)
    except KeyError:
        raise HTTPException(404, "Scan not found. Start a new scan.") from None
    if job["status"] != "completed" or job["result"] is None:
        raise HTTPException(409, "Wait for the scan to complete")
    cameras = [
        camera
        for categories in job["result"].values()
        for group in categories.values()
        for camera in group
    ]
    if camera_index < 0 or camera_index >= len(cameras):
        raise HTTPException(404, "Camera not found in scan results")
    data = dict(cameras[camera_index])
    if data.get("error") or data.get("protocol") != "onvif":
        raise HTTPException(
            409, "A successful ONVIF check is required before adding a camera"
        )
    for field in ("manufacturer", "model", "firmware", "serial_number", "mac_address"):
        data[field] = data.get(field) or ""
    cam = CameraCreate.model_validate(data)
    existing = db.exec(
        select(Camera).where(
            Camera.ip == cam.ip,
            Camera.port == cam.port,
            Camera.protocol == cam.protocol,
        )
    ).first()
    if existing:
        return {"id": existing.id, "already_exists": True}
    try:
        saved = add_cam(cam, db)
    except HTTPException as error:
        if error.status_code != 409:
            raise
        existing = db.exec(
            select(Camera).where(
                Camera.ip == cam.ip,
                Camera.port == cam.port,
                Camera.protocol == cam.protocol,
            )
        ).first()
        if existing is None:
            raise
        return {"id": existing.id, "already_exists": True}
    return {"id": saved.id, "already_exists": False}
