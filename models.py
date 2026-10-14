from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from database import Base


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    device_type: Mapped[str] = mapped_column(String(50))
    serial_number: Mapped[str] = mapped_column(String(100))
    location: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(50), default="в наличии")
    notes: Mapped[str | None] = mapped_column(String(500))