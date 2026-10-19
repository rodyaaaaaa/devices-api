from pydantic import BaseModel, ConfigDict

from domain.enums import DeviceType


class DeviceCreate(BaseModel):
    id: int
    name: str
    device_type: DeviceType
    serial_number: str
    location: str | None = None
    status: str = "в наличии"
    notes: str | None = None


class Device(DeviceCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
