"""Statute mapping endpoint (IPC/CrPC/IEA -> BNS/BNSS/BSA and reverse)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import ContainerDep, OptionalUser
from app.api.errors import responses
from app.core.exceptions import InvalidQueryError
from app.domain.acts import canonical_act
from app.schemas.common import BnsAlert

router = APIRouter(prefix="/statute", tags=["Statutes"])


@router.get(
    "/map", response_model=BnsAlert, summary="Map a provision between old and new criminal codes",
    description="IPC↔BNS, CrPC↔BNSS and IEA↔BSA from the curated mapping dataset (cross-checked with the knowledge "
    "graph when enabled). `mapping_type` is exact / approximate / no_mapping / ambiguous / unknown — the service "
    "never invents a correspondence. Examples: `IPC 302`, `IPC 304A`, `CrPC 438`, `BNS 318`.",
    responses=responses(401, 422),
)
async def map_statute(
    container: ContainerDep,
    user: OptionalUser,
    code: str = Query(min_length=2, max_length=40, examples=["IPC"]),
    section: str = Query(min_length=1, max_length=16, pattern=r"^\d{1,4}[A-Za-z]{0,3}(\(\d{1,3}\))?$", examples=["304A"]),
) -> BnsAlert:
    act = canonical_act(code)
    if act is None or not container.mapper.supports(act):
        raise InvalidQueryError(
            f"unsupported code {code!r}", public_message="Supported codes: IPC, BNS, CrPC, BNSS, IEA, BSA."
        )
    return BnsAlert.from_mapping(await container.mapper.map(act, section.upper()))
