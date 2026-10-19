from collections import Counter
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

import models
import schemas
from database import Base, SessionLocal, commit_or_409, engine, get_db, require
from reference import make_reference_router


def seed(db: Session):
    """Создаёт обязательные статусы и типы, если их ещё нет."""
    for model, names in (
        (models.Status, [models.STATUS_IN_STOCK, models.STATUS_ISSUED,
                         models.STATUS_REPAIR, models.STATUS_WRITTEN_OFF]),
        (models.DeviceType, [models.TYPE_TERMINAL, models.TYPE_ROUTER]),
    ):
        existing = set(db.scalars(select(model.name)))
        for name in names:
            if name not in existing:
                db.add(model(name=name))
    db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)  # создаёт таблицы, если их нет
    with SessionLocal() as db:
        seed(db)
    yield


app = FastAPI(title="Учёт терминалов и маршрутизаторов", lifespan=lifespan)


def get_status(db: Session, name: str) -> models.Status:
    return db.scalars(select(models.Status).where(models.Status.name == name)).one()


@app.get("/")
def root():
    return {"message": "Система учёта терминалов и маршрутизаторов"}


# =====================================================================
# Справочники (CRUD собирается универсальной функцией из reference.py)
# =====================================================================

app.include_router(make_reference_router(
    prefix="/device-types", tag="Справочники: типы устройств",
    model=models.DeviceType, create_schema=schemas.DeviceTypeIn, out_schema=schemas.DeviceTypeOut,
    label="тип устройства", in_use_message="Нельзя удалить: тип используется в моделях устройств",
))
app.include_router(make_reference_router(
    prefix="/manufacturers", tag="Справочники: производители",
    model=models.Manufacturer, create_schema=schemas.ManufacturerIn, out_schema=schemas.ManufacturerOut,
    label="производитель", in_use_message="Нельзя удалить: у производителя есть модели устройств",
))
app.include_router(make_reference_router(
    prefix="/locations", tag="Справочники: локации",
    model=models.Location, create_schema=schemas.LocationIn, out_schema=schemas.LocationOut,
    label="локация", in_use_message="Нельзя удалить: в этой локации есть устройства",
))
app.include_router(make_reference_router(
    prefix="/employees", tag="Справочники: сотрудники",
    model=models.Employee, create_schema=schemas.EmployeeIn, out_schema=schemas.EmployeeOut,
    label="сотрудник", in_use_message="Нельзя удалить: у сотрудника есть выдачи",
))
# Статусы системные (на них опирается логика выдачи), поэтому только чтение
app.include_router(make_reference_router(
    prefix="/statuses", tag="Справочники: статусы",
    model=models.Status, create_schema=None, out_schema=schemas.StatusOut,
    label="статус", in_use_message="", read_only=True,
))


# =====================================================================
# Модели устройств (производитель + тип + название, например Cisco 2901)
# =====================================================================

@app.get("/device-models", response_model=list[schemas.DeviceModelOut], tags=["Модели устройств"])
def get_device_models(
    manufacturer_id: int | None = None,
    device_type_id: int | None = None,
    db: Session = Depends(get_db),
):
    query = select(models.DeviceModel).order_by(models.DeviceModel.id)
    if manufacturer_id is not None:
        query = query.where(models.DeviceModel.manufacturer_id == manufacturer_id)
    if device_type_id is not None:
        query = query.where(models.DeviceModel.device_type_id == device_type_id)
    return db.scalars(query).all()


@app.post("/device-models", response_model=schemas.DeviceModelOut,
          status_code=status.HTTP_201_CREATED, tags=["Модели устройств"])
def create_device_model(data: schemas.DeviceModelIn, db: Session = Depends(get_db)):
    require(db, models.Manufacturer, data.manufacturer_id, "производитель")
    require(db, models.DeviceType, data.device_type_id, "тип устройства")
    item = models.DeviceModel(**data.model_dump())
    db.add(item)
    commit_or_409(db, "У этого производителя уже есть модель с таким названием")
    db.refresh(item)
    return item


@app.get("/device-models/{model_id}", response_model=schemas.DeviceModelOut, tags=["Модели устройств"])
def get_device_model(model_id: int, db: Session = Depends(get_db)):
    return require(db, models.DeviceModel, model_id, "модель устройства")


@app.put("/device-models/{model_id}", response_model=schemas.DeviceModelOut, tags=["Модели устройств"])
def update_device_model(model_id: int, data: schemas.DeviceModelIn, db: Session = Depends(get_db)):
    item = require(db, models.DeviceModel, model_id, "модель устройства")
    require(db, models.Manufacturer, data.manufacturer_id, "производитель")
    require(db, models.DeviceType, data.device_type_id, "тип устройства")
    for key, value in data.model_dump().items():
        setattr(item, key, value)
    commit_or_409(db, "У этого производителя уже есть модель с таким названием")
    db.refresh(item)
    return item


@app.delete("/device-models/{model_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Модели устройств"])
def delete_device_model(model_id: int, db: Session = Depends(get_db)):
    item = require(db, models.DeviceModel, model_id, "модель устройства")
    db.delete(item)
    commit_or_409(db, "Нельзя удалить: есть устройства этой модели")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =====================================================================
# Поступления: пришла партия устройств, регистрируем сразу все серийники
# =====================================================================

def delivery_out(db: Session, delivery: models.Delivery) -> schemas.DeliveryOut:
    """Собирает ответ: сама поставка и сколько каких моделей в ней пришло."""
    rows = db.execute(
        select(
            models.DeviceModel.id,
            models.Manufacturer.name,
            models.DeviceType.name,
            models.DeviceModel.name,
            func.count(models.Device.id),
        )
        .select_from(models.Device)
        .join(models.DeviceModel, models.DeviceModel.id == models.Device.device_model_id)
        .join(models.Manufacturer, models.Manufacturer.id == models.DeviceModel.manufacturer_id)
        .join(models.DeviceType, models.DeviceType.id == models.DeviceModel.device_type_id)
        .where(models.Device.delivery_id == delivery.id)
        .group_by(models.DeviceModel.id, models.Manufacturer.name,
                  models.DeviceType.name, models.DeviceModel.name)
        .order_by(models.Manufacturer.name, models.DeviceModel.name)
    ).all()
    items = [
        schemas.DeliveryLine(device_model_id=r[0], manufacturer=r[1], device_type=r[2], name=r[3], count=r[4])
        for r in rows
    ]
    return schemas.DeliveryOut(
        id=delivery.id,
        received_at=delivery.received_at,
        supplier=delivery.supplier,
        document_number=delivery.document_number,
        notes=delivery.notes,
        total=sum(i.count for i in items),
        items=items,
    )


@app.post("/deliveries", response_model=schemas.DeliveryOut,
          status_code=status.HTTP_201_CREATED, tags=["Поступления"])
def create_delivery(data: schemas.DeliveryCreate, db: Session = Depends(get_db)):
    if data.location_id is not None:
        require(db, models.Location, data.location_id, "локация")
    for item in data.items:
        require(db, models.DeviceModel, item.device_model_id, "модель устройства")

    serials = [s for item in data.items for s in item.serial_numbers]
    repeated = sorted(s for s, n in Counter(serials).items() if n > 1)
    if repeated:
        raise HTTPException(422, f"Серийные номера повторяются в запросе: {', '.join(repeated)}")
    existing = db.scalars(
        select(models.Device.serial_number).where(models.Device.serial_number.in_(serials))
    ).all()
    if existing:
        raise HTTPException(409, f"Эти серийные номера уже есть в базе: {', '.join(sorted(existing))}")

    in_stock = get_status(db, models.STATUS_IN_STOCK)
    delivery = models.Delivery(
        received_at=data.received_at,
        supplier=data.supplier,
        document_number=data.document_number,
        notes=data.notes,
    )
    db.add(delivery)
    db.flush()  # получаем delivery.id
    for item in data.items:
        for serial in item.serial_numbers:
            db.add(models.Device(
                device_model_id=item.device_model_id,
                delivery_id=delivery.id,
                serial_number=serial,
                status_id=in_stock.id,
                location_id=data.location_id,
            ))
    commit_or_409(db, "Не удалось сохранить поступление: серийный номер уже существует")
    return delivery_out(db, delivery)


@app.get("/deliveries", response_model=list[schemas.DeliveryOut], tags=["Поступления"])
def get_deliveries(
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = select(models.Delivery).order_by(models.Delivery.received_at.desc(), models.Delivery.id.desc())
    if date_from:
        query = query.where(models.Delivery.received_at >= date_from)
    if date_to:
        query = query.where(models.Delivery.received_at <= date_to)
    deliveries = db.scalars(query.limit(limit).offset(offset)).all()
    return [delivery_out(db, d) for d in deliveries]


@app.get("/deliveries/{delivery_id}", response_model=schemas.DeliveryOut, tags=["Поступления"])
def get_delivery(delivery_id: int, db: Session = Depends(get_db)):
    return delivery_out(db, require(db, models.Delivery, delivery_id, "поступление"))


# =====================================================================
# Устройства
# =====================================================================

# Получить все устройства (с фильтрами и постраничным выводом)
@app.get("/devices", response_model=list[schemas.DeviceOut], tags=["Устройства"])
def get_devices(
    device_type_id: int | None = None,
    manufacturer_id: int | None = None,
    device_model_id: int | None = None,
    status_id: int | None = None,
    location_id: int | None = None,
    delivery_id: int | None = None,
    serial: str | None = Query(None, description="Часть серийного номера"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = select(models.Device).join(
        models.DeviceModel, models.DeviceModel.id == models.Device.device_model_id
    )
    if device_type_id is not None:
        query = query.where(models.DeviceModel.device_type_id == device_type_id)
    if manufacturer_id is not None:
        query = query.where(models.DeviceModel.manufacturer_id == manufacturer_id)
    if device_model_id is not None:
        query = query.where(models.Device.device_model_id == device_model_id)
    if status_id is not None:
        query = query.where(models.Device.status_id == status_id)
    if location_id is not None:
        query = query.where(models.Device.location_id == location_id)
    if delivery_id is not None:
        query = query.where(models.Device.delivery_id == delivery_id)
    if serial:
        query = query.where(models.Device.serial_number.contains(serial))
    return db.scalars(query.order_by(models.Device.id).limit(limit).offset(offset)).all()


# Получить одно устройство
@app.get("/devices/{device_id}", response_model=schemas.DeviceOut, tags=["Устройства"])
def get_device(device_id: int, db: Session = Depends(get_db)):
    return require(db, models.Device, device_id, "устройство")


# Добавить одно устройство в существующее поступление
@app.post("/devices", response_model=schemas.DeviceOut,
          status_code=status.HTTP_201_CREATED, tags=["Устройства"])
def create_device(data: schemas.DeviceCreate, db: Session = Depends(get_db)):
    require(db, models.DeviceModel, data.device_model_id, "модель устройства")
    require(db, models.Delivery, data.delivery_id, "поступление")
    if data.location_id is not None:
        require(db, models.Location, data.location_id, "локация")
    device = models.Device(
        **data.model_dump(),
        status_id=get_status(db, models.STATUS_IN_STOCK).id,
    )
    db.add(device)
    commit_or_409(db, "Устройство с таким серийным номером уже есть")
    db.refresh(device)
    return device


# Обновить устройство
@app.put("/devices/{device_id}", response_model=schemas.DeviceOut, tags=["Устройства"])
def update_device(device_id: int, data: schemas.DeviceUpdate, db: Session = Depends(get_db)):
    device = require(db, models.Device, device_id, "устройство")
    require(db, models.DeviceModel, data.device_model_id, "модель устройства")
    require(db, models.Status, data.status_id, "статус")
    if data.location_id is not None:
        require(db, models.Location, data.location_id, "локация")

    # Статус «выдан» ставится и снимается только через выдачу и возврат,
    # иначе количество выданных устройств перестанет сходиться с историей.
    issued = get_status(db, models.STATUS_ISSUED)
    if data.status_id != device.status_id and issued.id in (data.status_id, device.status_id):
        raise HTTPException(409, "Статус «выдан» меняется только через /assignments (выдача и возврат)")

    for key, value in data.model_dump().items():
        setattr(device, key, value)
    commit_or_409(db, "Устройство с таким серийным номером уже есть")
    db.refresh(device)
    return device


# Удалить устройство (только если по нему нет истории выдач)
@app.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Устройства"])
def delete_device(device_id: int, db: Session = Depends(get_db)):
    device = require(db, models.Device, device_id, "устройство")
    has_history = db.scalar(
        select(func.count()).select_from(models.Assignment).where(models.Assignment.device_id == device_id)
    )
    if has_history:
        raise HTTPException(409, "Нельзя удалить: у устройства есть история выдач")
    db.delete(device)
    commit_or_409(db, "Нельзя удалить устройство")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# История выдач одного устройства
@app.get("/devices/{device_id}/history", response_model=list[schemas.AssignmentOut], tags=["Устройства"])
def get_device_history(device_id: int, db: Session = Depends(get_db)):
    require(db, models.Device, device_id, "устройство")
    query = (select(models.Assignment)
             .where(models.Assignment.device_id == device_id)
             .order_by(models.Assignment.issued_at.desc(), models.Assignment.id.desc()))
    return db.scalars(query).all()


# =====================================================================
# Выдача и возврат
# =====================================================================

# Выдать устройство сотруднику
@app.post("/assignments", response_model=schemas.AssignmentOut,
          status_code=status.HTTP_201_CREATED, tags=["Выдачи"])
def issue_device(data: schemas.AssignmentCreate, db: Session = Depends(get_db)):
    device = require(db, models.Device, data.device_id, "устройство")
    require(db, models.Employee, data.employee_id, "сотрудник")
    if device.status.name != models.STATUS_IN_STOCK:
        raise HTTPException(409, f"Устройство нельзя выдать: его статус «{device.status.name}»")

    assignment = models.Assignment(
        device_id=device.id, employee_id=data.employee_id, comment=data.comment
    )
    device.status = get_status(db, models.STATUS_ISSUED)
    db.add(assignment)
    commit_or_409(db, "Это устройство уже выдано")
    db.refresh(assignment)
    return assignment


# Принять устройство обратно
@app.post("/assignments/{assignment_id}/return", response_model=schemas.AssignmentOut, tags=["Выдачи"])
def return_device(
    assignment_id: int,
    data: schemas.AssignmentReturn | None = None,
    db: Session = Depends(get_db),
):
    assignment = require(db, models.Assignment, assignment_id, "выдача")
    if assignment.returned_at is not None:
        raise HTTPException(409, "Устройство уже возвращено")
    if data and data.location_id is not None:
        require(db, models.Location, data.location_id, "локация")
        assignment.device.location_id = data.location_id

    assignment.returned_at = datetime.now()
    assignment.device.status = get_status(db, models.STATUS_IN_STOCK)
    commit_or_409(db, "Не удалось оформить возврат")
    db.refresh(assignment)
    return assignment


# Список выдач (active=true: только устройства, которые сейчас на руках)
@app.get("/assignments", response_model=list[schemas.AssignmentOut], tags=["Выдачи"])
def get_assignments(
    device_id: int | None = None,
    employee_id: int | None = None,
    active: bool | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = select(models.Assignment)
    if device_id is not None:
        query = query.where(models.Assignment.device_id == device_id)
    if employee_id is not None:
        query = query.where(models.Assignment.employee_id == employee_id)
    if active is True:
        query = query.where(models.Assignment.returned_at.is_(None))
    elif active is False:
        query = query.where(models.Assignment.returned_at.is_not(None))
    query = query.order_by(models.Assignment.id.desc()).limit(limit).offset(offset)
    return db.scalars(query).all()


@app.get("/assignments/{assignment_id}", response_model=schemas.AssignmentOut, tags=["Выдачи"])
def get_assignment(assignment_id: int, db: Session = Depends(get_db)):
    return require(db, models.Assignment, assignment_id, "выдача")


# =====================================================================
# Отчёты: сколько пришло, сколько выдано, сколько осталось
# =====================================================================

def count_status(name: str):
    """Сколько устройств с данным статусом (для группировки по моделям)."""
    return func.coalesce(func.sum(case((models.Status.name == name, 1), else_=0)), 0)


# Остатки по моделям: сколько всего поступило, в наличии, выдано, в ремонте
@app.get("/stats/stock", response_model=schemas.StockReport, tags=["Отчёты"])
def stock_report(
    device_type_id: int | None = None,
    manufacturer_id: int | None = None,
    db: Session = Depends(get_db),
):
    query = (
        select(
            models.DeviceModel.id.label("device_model_id"),
            models.Manufacturer.name.label("manufacturer"),
            models.DeviceType.name.label("device_type"),
            models.DeviceModel.name.label("name"),
            func.count(models.Device.id).label("received"),
            count_status(models.STATUS_IN_STOCK).label("in_stock"),
            count_status(models.STATUS_ISSUED).label("issued"),
            count_status(models.STATUS_REPAIR).label("in_repair"),
            count_status(models.STATUS_WRITTEN_OFF).label("written_off"),
        )
        .select_from(models.DeviceModel)
        .join(models.Manufacturer, models.Manufacturer.id == models.DeviceModel.manufacturer_id)
        .join(models.DeviceType, models.DeviceType.id == models.DeviceModel.device_type_id)
        .outerjoin(models.Device, models.Device.device_model_id == models.DeviceModel.id)
        .outerjoin(models.Status, models.Status.id == models.Device.status_id)
        .group_by(models.DeviceModel.id, models.Manufacturer.name,
                  models.DeviceType.name, models.DeviceModel.name)
        .order_by(models.Manufacturer.name, models.DeviceModel.name)
    )
    if device_type_id is not None:
        query = query.where(models.DeviceModel.device_type_id == device_type_id)
    if manufacturer_id is not None:
        query = query.where(models.DeviceModel.manufacturer_id == manufacturer_id)

    items = [schemas.StockRow(**row._asdict()) for row in db.execute(query).all()]
    totals = schemas.StockCounts(
        **{field: sum(getattr(r, field) for r in items) for field in schemas.StockCounts.model_fields}
    )
    return schemas.StockReport(items=items, totals=totals)


# Движение за период: сколько поступило, выдано и возвращено
@app.get("/stats/movements", response_model=schemas.MovementReport, tags=["Отчёты"])
def movements_report(
    date_from: date | None = None,
    date_to: date | None = None,
    device_type_id: int | None = None,
    db: Session = Depends(get_db),
):
    start = datetime.combine(date_from, time.min) if date_from else None
    end = datetime.combine(date_to + timedelta(days=1), time.min) if date_to else None

    arrived_q = (
        select(models.Device.device_model_id, func.count(models.Device.id))
        .select_from(models.Device)
        .join(models.Delivery, models.Delivery.id == models.Device.delivery_id)
        .group_by(models.Device.device_model_id)
    )
    if date_from:
        arrived_q = arrived_q.where(models.Delivery.received_at >= date_from)
    if date_to:
        arrived_q = arrived_q.where(models.Delivery.received_at <= date_to)

    def assignments_q(column):
        q = (
            select(models.Device.device_model_id, func.count(models.Assignment.id))
            .select_from(models.Assignment)
            .join(models.Device, models.Device.id == models.Assignment.device_id)
            .where(column.is_not(None))
            .group_by(models.Device.device_model_id)
        )
        if start:
            q = q.where(column >= start)
        if end:
            q = q.where(column < end)
        return q

    arrived = dict(db.execute(arrived_q).all())
    issued = dict(db.execute(assignments_q(models.Assignment.issued_at)).all())
    returned = dict(db.execute(assignments_q(models.Assignment.returned_at)).all())

    names_q = (
        select(models.DeviceModel.id, models.Manufacturer.name, models.DeviceType.name, models.DeviceModel.name)
        .join(models.Manufacturer, models.Manufacturer.id == models.DeviceModel.manufacturer_id)
        .join(models.DeviceType, models.DeviceType.id == models.DeviceModel.device_type_id)
        .order_by(models.Manufacturer.name, models.DeviceModel.name)
    )
    if device_type_id is not None:
        names_q = names_q.where(models.DeviceModel.device_type_id == device_type_id)

    items = []
    for model_id, manufacturer, type_name, name in db.execute(names_q).all():
        row = schemas.MovementRow(
            device_model_id=model_id, manufacturer=manufacturer, device_type=type_name, name=name,
            arrived=arrived.get(model_id, 0),
            issued=issued.get(model_id, 0),
            returned=returned.get(model_id, 0),
        )
        if row.arrived or row.issued or row.returned:
            items.append(row)

    totals = schemas.MovementCounts(
        arrived=sum(r.arrived for r in items),
        issued=sum(r.issued for r in items),
        returned=sum(r.returned for r in items),
    )
    return schemas.MovementReport(date_from=date_from, date_to=date_to, items=items, totals=totals)