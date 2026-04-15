"""Line structure endpoints (SUPER_ADMIN only).

Allows editing part groups/parts and linking parts to stage graphs.
"""

from fastapi import Depends, HTTPException, Path, status

from beanie import PydanticObjectId

from mindtrace.apps.inspectra.core import get_inspectra_service, require_super_admin
from mindtrace.apps.inspectra.db import get_odm
from mindtrace.apps.inspectra.models import Part, PartGroup, StageGraph
from mindtrace.apps.inspectra.schemas.line_structure import (
    GetLineStructureSchema,
    LineStructureResponse,
    PartGroupItem,
    PartItem,
    UpdateLineStructureRequest,
    UpdateLineStructureSchema,
)


def _link_id(link) -> str:
    return str(link.ref.id) if hasattr(link, "ref") else str(link.id)


def register(service):
    deps = [Depends(require_super_admin)]
    service.add_endpoint(
        "/lines/{id}/structure",
        get_line_structure,
        schema=GetLineStructureSchema,
        methods=["GET"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/lines/{id}/structure",
        update_line_structure,
        schema=UpdateLineStructureSchema,
        methods=["PUT"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )


async def get_line_structure(
    id_: str = Path(alias="id"),
    service=Depends(get_inspectra_service),
):
    line = await service.line_repo.get(id_, fetch_links=True)
    if not line:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line not found")

    lid = PydanticObjectId(id_)
    groups = await PartGroup.find(PartGroup.line.id == lid, fetch_links=False).to_list()

    part_groups: list[PartGroupItem] = []
    for pg in groups:
        parts = await Part.find(Part.partgroup.id == pg.id, fetch_links=False).to_list()
        part_items: list[PartItem] = []
        for p in parts:
            sg_id = _link_id(p.stage_graph) if getattr(p, "stage_graph", None) else None
            sg_name = None
            if getattr(p, "stage_graph", None):
                try:
                    sg = await StageGraph.get(sg_id, fetch_links=False)
                    if sg:
                        sg_name = getattr(sg, "name", None)
                    else:
                        # dangling link to removed stage graph
                        sg_id = None
                except Exception:
                    sg_id = None
                    sg_name = None
            part_items.append(
                PartItem(
                    id=str(p.id),
                    part_number=p.part_number or "",
                    stage_graph_id=sg_id,
                    stage_graph_name=sg_name,
                )
            )
        part_groups.append(PartGroupItem(id=str(pg.id), name=pg.name or "", parts=part_items))

    return LineStructureResponse(line_id=str(line.id), part_groups=part_groups)


async def update_line_structure(
    payload: UpdateLineStructureRequest,
    id_: str = Path(alias="id"),
    service=Depends(get_inspectra_service),
):
    line = await service.line_repo.get(id_, fetch_links=True)
    if not line:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line not found")
    odm = get_odm()
    lid = PydanticObjectId(id_)

    # Uniqueness constraints:
    # - part group name unique within the line
    # - part number unique within the line
    seen_group_names: set[str] = set()
    seen_part_numbers: set[str] = set()
    for pg in payload.part_groups:
        name = (pg.name or "").strip()
        if not name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Part group name is required"
            )
        if name in seen_group_names:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f'Duplicate part group name: "{name}"',
            )
        seen_group_names.add(name)
        for part in pg.parts:
            pn = (part.part_number or "").strip()
            if not pn:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Part number is required"
                )
            if pn in seen_part_numbers:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f'Duplicate part number: "{pn}"',
                )
            seen_part_numbers.add(pn)

    existing_groups = await PartGroup.find(PartGroup.line.id == lid, fetch_links=False).to_list()
    existing_groups_by_id = {str(g.id): g for g in existing_groups}
    incoming_group_ids = {g.id for g in payload.part_groups if g.id}

    # Delete removed groups (and their parts/stages).
    for gid, grp in existing_groups_by_id.items():
        if gid not in incoming_group_ids:
            parts = await Part.find(Part.partgroup.id == grp.id, fetch_links=False).to_list()
            for p in parts:
                await odm.part.delete(p)
            await odm.part_group.delete(grp)

    # Upsert groups/parts/stages.
    for pg_in in payload.part_groups:
        if pg_in.id and pg_in.id in existing_groups_by_id:
            pg = existing_groups_by_id[pg_in.id]
            pg.name = pg_in.name
            pg = await odm.part_group.update(pg)
        else:
            pg = PartGroup(
                organization=line.organization,
                plant=line.plant,
                line=line,
                name=pg_in.name,
            )
            pg = await odm.part_group.insert(pg)

        existing_parts = await Part.find(Part.partgroup.id == pg.id, fetch_links=False).to_list()
        existing_parts_by_id = {str(p.id): p for p in existing_parts}
        incoming_part_ids = {p.id for p in pg_in.parts if p.id}

        for pid, part in existing_parts_by_id.items():
            if pid not in incoming_part_ids:
                await odm.part.delete(part)

        for part_in in pg_in.parts:
            if part_in.id and part_in.id in existing_parts_by_id:
                part = existing_parts_by_id[part_in.id]
                part.part_number = part_in.part_number
                if part_in.stage_graph_id:
                    try:
                        sg = await odm.stage_graph.get(part_in.stage_graph_id, fetch_links=False)
                    except Exception:
                        sg = None
                    part.stage_graph = sg
                else:
                    part.stage_graph = None
                part = await odm.part.update(part)
            else:
                sg = None
                if part_in.stage_graph_id:
                    try:
                        sg = await odm.stage_graph.get(part_in.stage_graph_id, fetch_links=False)
                    except Exception:
                        sg = None
                part = Part(
                    organization=line.organization,
                    line=line,
                    partgroup=pg,
                    part_number=part_in.part_number,
                    stage_graph=sg,
                )
                part = await odm.part.insert(part)

    return await get_line_structure(id_=id_, service=service)

