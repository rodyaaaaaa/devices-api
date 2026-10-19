"""Универсальный CRUD для простых справочников (типы, производители, локации, сотрудники).

Вместо того чтобы писать одинаковые 5 эндпоинтов для каждого справочника,
функция собирает их сама по переданным модели и схемам.
"""
from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import commit_or_409, get_db, require


def make_reference_router(
    *,
    prefix: str,
    tag: str,
    model,
    create_schema,
    out_schema,
    label: str,
    in_use_message: str,
    read_only: bool = False,
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=[tag])

    @router.get("", response_model=list[out_schema])
    def list_items(db: Session = Depends(get_db)):
        return db.scalars(select(model).order_by(model.id)).all()

    if read_only:
        return router

    @router.post("", response_model=out_schema, status_code=201)
    def create_item(data: create_schema, db: Session = Depends(get_db)):
        item = model(**data.model_dump())
        db.add(item)
        commit_or_409(db, "Такая запись уже существует")
        db.refresh(item)
        return item

    @router.get("/{item_id}", response_model=out_schema)
    def get_item(item_id: int, db: Session = Depends(get_db)):
        return require(db, model, item_id, label)

    @router.put("/{item_id}", response_model=out_schema)
    def update_item(item_id: int, data: create_schema, db: Session = Depends(get_db)):
        item = require(db, model, item_id, label)
        for key, value in data.model_dump().items():
            setattr(item, key, value)
        commit_or_409(db, "Такая запись уже существует")
        db.refresh(item)
        return item

    @router.delete("/{item_id}", status_code=204)
    def delete_item(item_id: int, db: Session = Depends(get_db)):
        item = require(db, model, item_id, label)
        db.delete(item)
        commit_or_409(db, in_use_message)
        return Response(status_code=204)

    return router