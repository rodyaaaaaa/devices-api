from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Enum as SQLAlchemyEnum
from database import Base

from .enums import DeviceType


class Manufactor(Base):
    __tablename__ = "manufactors"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(256))


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(128))
    device_type: Mapped[DeviceType] = mapped_column(SQLAlchemyEnum(DeviceType))
    volume: Mapped[int] = mapped_column(Integer, nullable=True)
    balance_count: Mapped[int] = mapped_column(Integer, default=0)

    manufactor_id: Mapped[int] = mapped_column(ForeignKey("manufactors.id"))

    manufactor: Mapped[Manufactor] = relationship(back_populates="devices")
