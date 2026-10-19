from fastapi import FastAPI, HTTPException, status, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

import models
from database import Base, engine, get_db
from schemas import Device, DeviceCreate, DeviceType

Base.metadata.create_all(bind=engine)  # создаёт таблицы, если их нет

app = FastAPI(title="Учёт терминалов и маршрутизаторов")


@app.get("/")
def root():
    return {"message": "Система учёта терминалов и маршрутизаторов"}


# Получить все устройства (можно фильтровать по типу)
@app.get("/devices", response_model=list[Device])
def get_devices(device_type: DeviceType | None = None, db: Session = Depends(get_db)):
    query = select(models.Device)
    if device_type:
        query = query.where(models.Device.device_type == device_type.value)
    return db.scalars(query).all()


# Получить одно устройство
@app.get("/devices/{device_id}", response_model=Device)
def get_device(device_id: int, db: Session = Depends(get_db)):
    device = db.get(models.Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Устройство не найдено")
    return device


# Добавить устройство
@app.post("/devices", response_model=Device, status_code=status.HTTP_201_CREATED)
def create_device(data: DeviceCreate, db: Session = Depends(get_db)):
    device = models.Device(**data.model_dump(mode="json"))
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


# Обновить устройство
@app.put("/devices/{device_id}", response_model=Device)
def update_device(device_id: int, data: DeviceCreate, db: Session = Depends(get_db)):
    device = db.get(models.Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Устройство не найдено")
    for key, value in data.model_dump(mode="json").items():
        setattr(device, key, value)
    db.commit()
    db.refresh(device)
    return device


# Удалить устройство
@app.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_device(device_id: int, db: Session = Depends(get_db)):
    device = db.get(models.Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Устройство не найдено")
    db.delete(device)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)