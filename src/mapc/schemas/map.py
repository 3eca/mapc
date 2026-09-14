from pydantic import BaseModel, ConfigDict, Field


class MapResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    mime_type: str
    width: int
    height: int


class PlacementInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    direction: float = Field(default=0, ge=0, lt=360)
    view_angle: float = Field(default=90, gt=0, le=360)
    view_distance: float = Field(default=0.1, gt=0, le=2)


class PlacementResponse(PlacementInput):
    model_config = ConfigDict(from_attributes=True)
    id: int
    map_id: int
    camera_id: int
