from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

# Названия, на которые опирается логика. Создаются автоматически при старте.
STATUS_IN_STOCK = "в наличии"
STATUS_ISSUED = "выдан"
STATUS_REPAIR = "в ремонте"
STATUS_WRITTEN_OFF = "списан"
TYPE_TERMINAL = "терминал"
TYPE_ROUTER = "маршрутизатор"


# ---------- справочники ----------

class DeviceType(Base):
    __tablename__ = "device_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)


class Manufacturer(Base):
    __tablename__ = "manufacturers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)


class Status(Base):
    __tablename__ = "statuses"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    address: Mapped[str | None] = mapped_column(String(300))


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    position: Mapped[str | None] = mapped_column(String(100))


# ---------- модель устройства (производитель + тип + название) ----------

class DeviceModel(Base):
    __tablename__ = "device_models"
    __table_args__ = (UniqueConstraint("manufacturer_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    manufacturer_id: Mapped[int] = mapped_column(ForeignKey("manufacturers.id"))
    device_type_id: Mapped[int] = mapped_column(ForeignKey("device_types.id"))
    name: Mapped[str] = mapped_column(String(100))

    manufacturer: Mapped[Manufacturer] = relationship(lazy="joined")
    device_type: Mapped[DeviceType] = relationship(lazy="joined")


# ---------- поступление (накладная) ----------

class Delivery(Base):
    __tablename__ = "deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    received_at: Mapped[date] = mapped_column(Date, default=date.today)
    supplier: Mapped[str | None] = mapped_column(String(200))
    document_number: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(String(500))


# ---------- конкретное устройство ----------

class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_model_id: Mapped[int] = mapped_column(ForeignKey("device_models.id"))
    delivery_id: Mapped[int] = mapped_column(ForeignKey("deliveries.id"))
    serial_number: Mapped[str] = mapped_column(String(100), unique=True)
    status_id: Mapped[int] = mapped_column(ForeignKey("statuses.id"))
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    notes: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    device_model: Mapped[DeviceModel] = relationship(lazy="joined")
    status: Mapped[Status] = relationship(lazy="joined")
    location: Mapped[Location | None] = relationship(lazy="joined")


# ---------- выдача устройства сотруднику ----------

class Assignment(Base):
    __tablename__ = "assignments"
    # Одно устройство не может быть выдано дважды одновременно:
    # строка с returned_at IS NULL (устройство на руках) может быть только одна.
    __table_args__ = (
        Index(
            "uq_assignments_open_device",
            "device_id",
            unique=True,
            sqlite_where=text("returned_at IS NULL"),
            postgresql_where=text("returned_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime)
    comment: Mapped[str | None] = mapped_column(String(500))

    device: Mapped[Device] = relationship(lazy="joined")
    employee: Mapped[Employee] = relationship(lazy="joined")