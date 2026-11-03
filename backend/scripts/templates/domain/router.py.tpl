import uuid

from dependency_injector.wiring import inject
from fastapi import APIRouter, Response

from src.api.__domain__.schemas import __Entity__CreateRequest, __Entity__Response, __Entity__UpdateRequest
from src.api.deps import __Entity__ServiceDep, Pagination
from src.shared.responses import Envelope, paginated, success

router = APIRouter(prefix="/__route__", tags=["__Title__"])


@router.post("", status_code=201, response_model=Envelope[__Entity__Response])
@inject
async def create___entity__(body: __Entity__CreateRequest, service: __Entity__ServiceDep):
    return success(await service.create(**body.model_dump()), message="__Entity__ created")


@router.get("", response_model=Envelope[list[__Entity__Response]])
@inject
async def list___domain__(pagination: Pagination, service: __Entity__ServiceDep):
    return paginated(await service.get_page(page=pagination.page, page_size=pagination.page_size))


@router.get("/{__entity___id}", response_model=Envelope[__Entity__Response])
@inject
async def get___entity__(__entity___id: uuid.UUID, service: __Entity__ServiceDep):
    return success(await service.get(__entity___id))


@router.patch("/{__entity___id}", response_model=Envelope[__Entity__Response])
@inject
async def update___entity__(__entity___id: uuid.UUID, body: __Entity__UpdateRequest, service: __Entity__ServiceDep):
    fields = body.model_dump(exclude_unset=True)
    return success(await service.update(__entity___id, fields), message="__Entity__ updated")


@router.delete("/{__entity___id}", status_code=204, response_class=Response)
@inject
async def delete___entity__(__entity___id: uuid.UUID, service: __Entity__ServiceDep):
    await service.delete(__entity___id)
    return Response(status_code=204)
