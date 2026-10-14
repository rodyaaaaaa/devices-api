from enum import Enum
from pydantic import BaseModel, ConfigDict


class DeviceType(str, Enum):
    terminal_HV = "терминал HikVision"
    terminal_Dahua = "терминал Dahua"
    marshrutizator = "маршрутизатор"


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