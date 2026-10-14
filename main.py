from fastapi import FastAPI, HTTPException, status, Query
from pydantic import BaseModel
from enum import Enum

app = FastAPI(title="Учёт терминалов и маршрутизаторов")

# Тип устройства
class DeviceType(str, Enum):
    terminal_HV = "терминал HikVision"
    terminal_Dahua = "терминал Dahua"
    marshrutizator = "маршрутизатор"

# Модель для создания устройства
class DeviceCreate(BaseModel):
    name: str                          # Название (например, "Cisco 2901")
    device_type: DeviceType            # terminal или router
    serial_number: str                 # Серийный номер
    location: str | None = None        # Где находится
    status: str = "в наличии"          # в наличии / выдан / в ремонте
    notes: str | None = None           # Примечание

# Полная модель (с ID)
class Device(DeviceCreate):
    id: int

# База данных в памяти
db: list[Device] = []
next_id = 1

@app.get("/")
def root():
    return {"message": "Система учёта терминалов и маршрутизаторов"}

# Получить все устройства (можно фильтровать по типу)
@app.get("/devices", response_model=list[Device])
def get_devices(device_type: DeviceType | None = None):
    if device_type:
        return [d for d in db if d.device_type == device_type]
    return db

# Получить одно устройство
@app.get("/devices/{device_id}", response_model=Device)
def get_device(device_id: int):
    for device in db:
        if device.id == device_id:
            return device
    raise HTTPException(status_code=404, detail="Устройство не найдено")

# Добавить устройство
@app.post("/devices", response_model=Device, status_code=status.HTTP_201_CREATED)
def create_device(device: DeviceCreate):
    global next_id
    new_device = Device(id=next_id, **device.model_dump())
    db.append(new_device)
    next_id += 1
    return new_device

# Обновить устройство
@app.put("/devices/{device_id}", response_model=Device)
def update_device(device_id: int, device: DeviceCreate):
    for index, existing in enumerate(db):
        if existing.id == device_id:
            updated = Device(id=device_id, **device.model_dump())
            db[index] = updated
            return updated
    raise HTTPException(status_code=404, detail="Устройство не найдено")

# Удалить устройство
@app.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_device(device_id: int):
    for index, device in enumerate(db):
        if device.id == device_id:
            db.pop(index)
            return
    raise HTTPException(status_code=404, detail="Устройство не найдено")