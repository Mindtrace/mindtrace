"""
Model repository for Inspectra using Mindtrace ODM.

Provides list/get/create/update operations for Model documents. Models are linked to ModelVersion.
"""

from typing import List, Optional

from mindtrace.apps.inspectra.db import get_odm
from mindtrace.apps.inspectra.models import Model, ModelVersion


class ModelRepository:
    """Model queries via MongoMindtraceODM."""

    async def get(self, model_id: str, fetch_links: bool = True) -> Optional[Model]:
        odm = get_odm()
        try:
            return await odm.model.get(model_id, fetch_links=fetch_links)
        except Exception:
            return None

    async def list_all(self, skip: int = 0, limit: int = 0) -> List[Model]:
        odm = get_odm()
        max_limit = limit if limit else 500
        return await odm.model.find(skip=skip, limit=max_limit, fetch_links=True)

    async def count_all(self) -> int:
        return await Model.count()

    async def create(self, name: str, version: str) -> Optional[Model]:
        odm = get_odm()
        model = Model(name=name, version=None)
        model = await odm.model.insert(model)
        mv = ModelVersion(model=model, version=version, model_deployment=None)
        mv = await odm.model_version.insert(mv)
        model.version = mv
        return await odm.model.update(model)

    async def update(
        self,
        model_id: str,
        *,
        name: Optional[str] = None,
        version: Optional[str] = None,
    ) -> Optional[Model]:
        model = await self.get(model_id, fetch_links=True)
        if not model:
            return None
        odm = get_odm()
        if name is not None:
            model.name = name
        if version is not None:
            if model.version is not None:
                model_version = model.version
                if hasattr(model_version, "version"):
                    model_version.version = version
                    await odm.model_version.update(model_version)
            else:
                mv = ModelVersion(model=model, version=version, model_deployment=None)
                mv = await odm.model_version.insert(mv)
                model.version = mv
        return await odm.model.update(model)

