from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# Серийный номер: без пробелов по краям, от 1 до 100 символов
Serial = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class InModel(BaseModel):
    """Базовый класс для данных, которые приходят в API."""
    model_config = ConfigDict(str_strip_whitespace=True)


class OutModel(BaseModel):
    """Базовый класс для ответов: умеет читать объекты SQLAlchemy."""
    model_config = ConfigDict(from_attributes=True)


# ---------- справочники ----------

class DeviceTypeIn(InModel):
    name: str = Field(min_length=1, max_length=50)


class DeviceTypeOut(OutModel):
    id: int
    name: str


class ManufacturerIn(InModel):
    name: str = Field(min_length=1, max_length=100)


class ManufacturerOut(OutModel):
    id: int
    name: str


class StatusOut(OutModel):
    id: int
    name: str


class LocationIn(InModel):
    name: str = Field(min_length=1, max_length=200)
    address: str | None = Field(default=None, max_length=300)


class LocationOut(OutModel):
    id: int
    name: str
    address: str | None


class EmployeeIn(InModel):
    full_name: str = Field(min_length=1, max_length=200)
    position: str | None = Field(default=None, max_length=100)


class EmployeeOut(OutModel):
    id: int
    full_name: str
    position: str | None


# ---------- модели устройств ----------

class DeviceModelIn(InModel):
    manufacturer_id: int
    device_type_id: int
    name: str = Field(min_length=1, max_length=100)


class DeviceModelOut(OutModel):
    id: int
    name: str
    manufacturer: ManufacturerOut
    device_type: DeviceTypeOut


# ---------- устройства ----------

class DeviceCreate(InModel):
    device_model_id: int
    delivery_id: int
    serial_number: Serial
    location_id: int | None = None
    notes: str | None = Field(default=None, max_length=500)


class DeviceUpdate(InModel):
    device_model_id: int
    serial_number: Serial
    status_id: int
    location_id: int | None = None
    notes: str | None = Field(default=None, max_length=500)


class DeviceOut(OutModel):
    id: int
    serial_number: str
    notes: str | None
    created_at: datetime
    delivery_id: int
    device_model: DeviceModelOut
    status: StatusOut
    location: LocationOut | None


# ---------- поступления ----------

class DeliveryItem(InModel):
    device_model_id: int
    serial_numbers: list[Serial] = Field(min_length=1)


class DeliveryCreate(InModel):
    received_at: date = Field(default_factory=date.today)
    supplier: str | None = Field(default=None, max_length=200)
    document_number: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=500)
    location_id: int | None = None   # куда положили устройства
    items: list[DeliveryItem] = Field(min_length=1)


class DeliveryLine(BaseModel):
    device_model_id: int
    manufacturer: str
    device_type: str
    name: str
    count: int


class DeliveryOut(BaseModel):
    id: int
    received_at: date
    supplier: str | None
    document_number: str | None
    notes: str | None
    total: int
    items: list[DeliveryLine]


# ---------- выдачи ----------

class AssignmentCreate(InModel):
    device_id: int
    employee_id: int
    comment: str | None = Field(default=None, max_length=500)


class AssignmentReturn(InModel):
    location_id: int | None = None   # куда вернули устройство


class AssignmentOut(OutModel):
    id: int
    issued_at: datetime
    returned_at: datetime | None
    comment: str | None
    device: DeviceOut
    employee: EmployeeOut


# ---------- отчёты ----------

class StockCounts(BaseModel):
    received: int = 0      # всего поступило
    in_stock: int = 0      # в наличии
    issued: int = 0        # сейчас на руках
    in_repair: int = 0     # в ремонте
    written_off: int = 0   # списано


class StockRow(StockCounts):
    device_model_id: int
    manufacturer: str
    device_type: str
    name: str


class StockReport(BaseModel):
    items: list[StockRow]
    totals: StockCounts


class MovementCounts(BaseModel):
    arrived: int = 0    # поступило за период
    issued: int = 0     # выдано за период
    returned: int = 0   # возвращено за период


class MovementRow(MovementCounts):
    device_model_id: int
    manufacturer: str
    device_type: str
    name: str


class MovementReport(BaseModel):
    date_from: date | None
    date_to: date | None
    items: list[MovementRow]
    totals: MovementCounts