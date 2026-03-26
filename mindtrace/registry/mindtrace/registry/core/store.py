"""Store facade for working with multiple Registries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Type

from zenml.materializers.base_materializer import BaseMaterializer

from mindtrace.core import Mindtrace
from mindtrace.registry.backends.local_registry_backend import LocalRegistryBackend
from mindtrace.registry.core.exceptions import (
    RegistryObjectNotFound,
    StoreAmbiguousObjectError,
    StoreKeyFormatError,
    StoreLocationNotFound,
)
from mindtrace.registry.core.registry import Registry
from mindtrace.registry.core.types import BatchResult, VerifyLevel


@dataclass(frozen=True)
class StoreMount:
    name: str
    registry: Registry
    read_only: bool = False


class Store(Mindtrace):
    """Facade that routes operations to multiple registries.

    Key formats:
      - Qualified: ``<mount>/<name>[@<version>]``
      - Unqualified: ``<name>[@<version>]``
    """

    def __init__(
        self,
        mounts: dict[str, Registry] | None = None,
        *,
        default_mount: str = "local",
        enable_location_cache: bool = True,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self._mounts: dict[str, StoreMount] = {}
        self._name_location_cache: dict[str, list[str]] = {}
        self._enable_location_cache = enable_location_cache

        store_dir = Path(self.config["MINDTRACE_DIR_PATHS"]["STORE_DIR"]).expanduser().resolve()
        self.add_mount("local", Registry(backend=LocalRegistryBackend(uri=store_dir), **kwargs))

        mounts = mounts or {}
        for mount_name, registry in mounts.items():
            if mount_name == "local":
                self._mounts["local"] = StoreMount(name="local", registry=registry, read_only=False)
            else:
                self.add_mount(mount_name, registry)

        self.set_default_mount(default_mount)

    def set_default_mount(self, mount: str) -> None:
        if mount not in self._mounts:
            raise StoreLocationNotFound(f"Default mount '{mount}' is not configured")
        self.default_mount = mount

    def add_mount(self, mount: str, registry: Registry, *, read_only: bool = False) -> None:
        if not mount or "/" in mount or "@" in mount:
            raise ValueError("Invalid mount name")
        if mount in self._mounts:
            raise ValueError(f"Mount '{mount}' already exists")
        self._mounts[mount] = StoreMount(name=mount, registry=registry, read_only=read_only)

    def remove_mount(self, mount: str) -> None:
        if mount == "local":
            raise ValueError("Cannot remove required local mount")
        if mount not in self._mounts:
            raise StoreLocationNotFound(mount)
        del self._mounts[mount]
        for name, mounts in list(self._name_location_cache.items()):
            remaining = [m for m in mounts if m != mount]
            if remaining:
                self._name_location_cache[name] = remaining
            else:
                self._name_location_cache.pop(name, None)
        if self.default_mount == mount:
            self.default_mount = "local"

    def get_mount(self, mount: str) -> StoreMount:
        store_mount = self._mounts.get(mount)
        if store_mount is None:
            raise StoreLocationNotFound(mount)
        return store_mount

    def has_mount(self, mount: str) -> bool:
        return mount in self._mounts

    def list_mounts(self) -> list[str]:
        return list(self._mounts.keys())

    def list_mount_info(self) -> dict[str, dict[str, Any]]:
        return {
            name: {
                "read_only": mount.read_only,
                "backend": str(mount.registry.backend.uri),
                "version_objects": mount.registry.version_objects,
                "mutable": mount.registry.mutable,
                "version_digits": mount.registry.version_digits,
            }
            for name, mount in self._mounts.items()
        }

    def parse_key(self, key: str) -> tuple[str | None, str, str | None]:
        if not key or not key.strip():
            raise StoreKeyFormatError("Key cannot be empty")

        raw = key.strip()
        base, version = raw.split("@", 1) if "@" in raw else (raw, None)

        if not base:
            raise StoreKeyFormatError(f"Invalid key: {key}")

        if "/" in base:
            candidate_mount, remainder = base.split("/", 1)
            if candidate_mount in self._mounts:
                if not remainder:
                    raise StoreKeyFormatError(f"Invalid key: {key}")
                return candidate_mount, remainder, version

        return None, base, version

    def build_key(self, mount: str, name: str, version: str | None = None) -> str:
        if mount not in self._mounts:
            raise StoreLocationNotFound(mount)
        if not name:
            raise StoreKeyFormatError("name cannot be empty")
        return f"{mount}/{name}" if version is None else f"{mount}/{name}@{version}"

    def resolve_registry(self, key_or_mount: str) -> Registry:
        if key_or_mount in self._mounts:
            return self._mounts[key_or_mount].registry
        mount, _, _ = self.parse_key(key_or_mount)
        if mount is None:
            raise StoreLocationNotFound("No mount specified")
        return self._mounts[mount].registry

    def cache_lookup_locations(self, name: str) -> list[str]:
        if not self._enable_location_cache:
            return []
        return list(self._name_location_cache.get(name, []))

    def cache_update_location(self, name: str, mount: str) -> None:
        if not self._enable_location_cache:
            return
        current = self._name_location_cache.get(name, [])
        if mount in current:
            current = [mount] + [m for m in current if m != mount]
        else:
            current = [mount] + current
        self._name_location_cache[name] = current

    def cache_evict_name(self, name: str) -> None:
        self._name_location_cache.pop(name, None)

    def clear_location_cache(self) -> None:
        self._name_location_cache.clear()

    def _resolve_load_location(self, name: str, version: str | None) -> str:
        ordered_mounts: list[str] = []

        for mount in self.cache_lookup_locations(name):
            if mount in self._mounts and mount not in ordered_mounts:
                ordered_mounts.append(mount)

        for mount in self._mounts:
            if mount not in ordered_mounts:
                ordered_mounts.append(mount)

        hits: list[str] = []
        for mount in ordered_mounts:
            if self._mounts[mount].registry.has_object(name, version or "latest"):
                hits.append(mount)

        if not hits:
            raise RegistryObjectNotFound(f"Object {name}@{version or 'latest'} not found in any store mount")

        if len(hits) > 1:
            mounts = ", ".join(hits)
            raise StoreAmbiguousObjectError(
                f"Object '{name}' found in multiple mounts: {mounts}. "
                f"Use an explicit key, e.g. '{hits[0]}/{name}'."
            )

        mount = hits[0]
        self.cache_update_location(name, mount)
        return mount

    def _single_save(
        self,
        key: str,
        obj: Any,
        *,
        materializer: Type[BaseMaterializer] | None = None,
        version: str | None = None,
        init_params: Dict[str, Any] | None = None,
        metadata: Dict[str, Any] | None = None,
        on_conflict: str | None = None,
    ) -> str | None:
        mount, name, key_version = self.parse_key(key)
        if mount is None:
            mount = self.default_mount
        store_mount = self.get_mount(mount)
        if store_mount.read_only:
            raise PermissionError(f"Mount '{mount}' is read-only")

        resolved_version = version if version is not None else key_version
        out = store_mount.registry.save(
            name,
            obj,
            materializer=materializer,
            version=resolved_version,
            init_params=init_params,
            metadata=metadata,
            on_conflict=on_conflict,
        )
        self.cache_update_location(name, mount)
        return out

    def save(
        self,
        name: str | List[str],
        obj: Any | List[Any],
        *,
        materializer: Type[BaseMaterializer] | None = None,
        version: str | None | List[str | None] = None,
        init_params: Dict[str, Any] | List[Dict[str, Any]] | None = None,
        metadata: Dict[str, Any] | List[Dict[str, Any]] | None = None,
        on_conflict: str | None = None,
    ) -> str | None | BatchResult:
        if isinstance(name, str):
            return self._single_save(
                name,
                obj,
                materializer=materializer,
                version=version if isinstance(version, str) or version is None else version[0],
                init_params=init_params if isinstance(init_params, dict) or init_params is None else init_params[0],
                metadata=metadata if isinstance(metadata, dict) or metadata is None else metadata[0],
                on_conflict=on_conflict,
            )

        objs = obj if isinstance(obj, list) else [obj] * len(name)
        versions = version if isinstance(version, list) else [version] * len(name)
        init_params_list = init_params if isinstance(init_params, list) else [init_params] * len(name)
        metadata_list = metadata if isinstance(metadata, list) else [metadata] * len(name)

        if not (len(name) == len(objs) == len(versions)):
            raise ValueError("name, obj, and version list lengths must match")

        result = BatchResult()
        for i, key in enumerate(name):
            try:
                v = self._single_save(
                    key,
                    objs[i],
                    materializer=materializer,
                    version=versions[i],
                    init_params=init_params_list[i],
                    metadata=metadata_list[i],
                    on_conflict=on_conflict,
                )
                result.results.append(v)
                mount, object_name, _ = self.parse_key(key)
                mount_name = mount or self.default_mount
                result.succeeded.append((f"{mount_name}/{object_name}", v or "latest"))
            except Exception as e:
                result.results.append(None)
                mount, object_name, key_version = self.parse_key(key)
                ver = versions[i] or key_version or "latest"
                mount_name = mount or self.default_mount
                item_key = (f"{mount_name}/{object_name}", ver)
                result.failed.append(item_key)
                result.errors[item_key] = {"error": type(e).__name__, "message": str(e)}
        return result

    def _single_load(
        self,
        key: str,
        version: str | None = "latest",
        output_dir: str | None = None,
        verify: str = VerifyLevel.INTEGRITY,
        **kwargs,
    ) -> Any:
        mount, name, key_version = self.parse_key(key)
        resolved_version = version if version not in (None, "latest") else (key_version or version)

        if mount is not None:
            store_mount = self.get_mount(mount)
            obj = store_mount.registry.load(name, version=resolved_version, output_dir=output_dir, verify=verify, **kwargs)
            self.cache_update_location(name, mount)
            return obj

        resolved_mount = self._resolve_load_location(name, resolved_version)
        return self._mounts[resolved_mount].registry.load(
            name,
            version=resolved_version,
            output_dir=output_dir,
            verify=verify,
            **kwargs,
        )

    def load(
        self,
        name: str | List[str],
        version: str | None | List[str | None] = "latest",
        output_dir: str | None = None,
        verify: str = VerifyLevel.INTEGRITY,
        **kwargs,
    ) -> Any | BatchResult:
        if isinstance(name, str):
            return self._single_load(
                name,
                version if isinstance(version, str) or version is None else version[0],
                output_dir,
                verify,
                **kwargs,
            )

        versions = version if isinstance(version, list) else [version] * len(name)
        if len(name) != len(versions):
            raise ValueError("name and version lists must have same length")

        result = BatchResult()
        for i, key in enumerate(name):
            try:
                obj = self._single_load(key, versions[i], output_dir=output_dir, verify=verify, **kwargs)
                result.results.append(obj)
                result.succeeded.append((key, versions[i] or "latest"))
            except Exception as e:
                result.results.append(None)
                k = (key, versions[i] or "latest")
                result.failed.append(k)
                result.errors[k] = {"error": type(e).__name__, "message": str(e)}
        return result

    def _single_delete(self, key: str, version: str | None = None) -> None:
        mount, name, key_version = self.parse_key(key)
        if mount is None:
            mount = self.default_mount
        store_mount = self.get_mount(mount)
        if store_mount.read_only:
            raise PermissionError(f"Mount '{mount}' is read-only")
        store_mount.registry.delete(name, version if version is not None else key_version)
        self.cache_evict_name(name)

    def delete(self, name: str | List[str], version: str | None | List[str | None] = None) -> None | BatchResult:
        if isinstance(name, str):
            self._single_delete(name, version if isinstance(version, str) or version is None else version[0])
            return None

        versions = version if isinstance(version, list) else [version] * len(name)
        if len(name) != len(versions):
            raise ValueError("name and version lists must have same length")

        result = BatchResult()
        for i, key in enumerate(name):
            try:
                self._single_delete(key, versions[i])
                result.results.append(None)
                result.succeeded.append((key, versions[i] or "latest"))
            except Exception as e:
                result.results.append(None)
                k = (key, versions[i] or "latest")
                result.failed.append(k)
                result.errors[k] = {"error": type(e).__name__, "message": str(e)}
        return result

    def has_object(self, name: str, version: str = "latest") -> bool:
        mount, object_name, key_version = self.parse_key(name)
        check_version = version if version != "latest" else (key_version or "latest")

        if mount is not None:
            return self.get_mount(mount).registry.has_object(object_name, check_version)

        for store_mount in self._mounts.values():
            if store_mount.registry.has_object(object_name, check_version):
                return True
        return False

    def list_objects(self, mount: str | None = None) -> list[str]:
        if mount is not None:
            store_mount = self.get_mount(mount)
            return [self.build_key(mount, n) for n in store_mount.registry.list_objects()]

        out: list[str] = []
        for mount_name, store_mount in self._mounts.items():
            out.extend(self.build_key(mount_name, n) for n in store_mount.registry.list_objects())
        return out

    def list_versions(self, name: str) -> list[str]:
        mount, object_name, _ = self.parse_key(name)
        if mount is None:
            raise StoreKeyFormatError("list_versions requires qualified key: <mount>/<name>")
        return self.get_mount(mount).registry.list_versions(object_name)

    def list_objects_and_versions(self, mount: str | None = None) -> dict[str, list[str]]:
        if mount is not None:
            store_mount = self.get_mount(mount)
            return {self.build_key(mount, k): v for k, v in store_mount.registry.list_objects_and_versions().items()}

        out: dict[str, list[str]] = {}
        for mount_name, store_mount in self._mounts.items():
            for name, versions in store_mount.registry.list_objects_and_versions().items():
                out[self.build_key(mount_name, name)] = versions
        return out

    def info(self, name: str | None = None, version: str | None = None) -> Dict[str, Any]:
        if name is None:
            return {
                "default_mount": self.default_mount,
                "mounts": self.list_mount_info(),
            }

        mount, object_name, key_version = self.parse_key(name)
        if mount is None:
            mount = self._resolve_load_location(object_name, version or key_version)
        return self.get_mount(mount).registry.info(object_name, version=version or key_version)

    def copy(
        self,
        source: str,
        *,
        target: str,
        source_version: str = "latest",
        target_version: str | None = None,
    ) -> str:
        obj = self.load(source, version=source_version)
        saved = self.save(target, obj, version=target_version)
        return saved if isinstance(saved, str) else (target_version or "latest")

    def move(
        self,
        source: str,
        *,
        target: str,
        source_version: str = "latest",
        target_version: str | None = None,
    ) -> str:
        saved = self.copy(source, target=target, source_version=source_version, target_version=target_version)
        self.delete(source, version=source_version)
        return saved

    def __getitem__(self, key: str | list[str]) -> Any:
        return self.load(key)

    def __setitem__(self, key: str | list[str], value: Any) -> None:
        self.save(key, value)

    def __delitem__(self, key: str | list[str]) -> None:
        self.delete(key)

    def __contains__(self, key: str | list[str]) -> bool:
        if isinstance(key, list):
            return all(self.__contains__(k) for k in key)
        return self.has_object(key)

    def __len__(self) -> int:
        return sum(len(store_mount.registry) for store_mount in self._mounts.values())

    def __str__(self, *, color: bool = True, latest_only: bool = True) -> str:
        sections = ["Store"]
        for mount_name, store_mount in self._mounts.items():
            marker = "*" if mount_name == self.default_mount else ""
            sections.append(f"[{mount_name}{marker}]\n{store_mount.registry.__str__(color=color, latest_only=latest_only)}")
        sections.append(f"Default Mount: `{self.default_mount}`")
        return "\n\n".join(sections)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except RegistryObjectNotFound:
            return default

    def keys(self, mount: str | None = None) -> list[str]:
        return self.list_objects(mount=mount)

    def values(self, mount: str | None = None) -> list[Any]:
        return [self.load(k) for k in self.keys(mount=mount)]

    def items(self, mount: str | None = None) -> list[tuple[str, Any]]:
        keys = self.keys(mount=mount)
        return [(k, self.load(k)) for k in keys]

    def pop(self, key: str, default: Any = None) -> Any:
        mount, name, key_version = self.parse_key(key)
        delete_key = key
        load_version = key_version or "latest"

        if mount is None:
            try:
                mount = self._resolve_load_location(name, key_version or "latest")
            except RegistryObjectNotFound:
                if default is not None:
                    return default
                raise
            delete_key = self.build_key(mount, name, key_version)

        value = self.load(key, version=load_version)
        self.delete(delete_key, version=key_version)
        return value

    def setdefault(self, key: str, default: Any = None) -> Any:
        try:
            return self.load(key)
        except RegistryObjectNotFound:
            if default is not None:
                self.save(key, default)
            return default

    def update(self, mapping, *, sync_all_versions: bool = True) -> None:
        if isinstance(mapping, Store):
            if sync_all_versions:
                for mount in mapping.list_mounts():
                    for name, versions in mapping.get_mount(mount).registry.list_objects_and_versions().items():
                        target_key = self.build_key(self.default_mount, name)
                        for version in versions:
                            self.save(target_key, mapping.load(mapping.build_key(mount, name), version=version), version=version)
                return

            for mount in mapping.list_mounts():
                for name in mapping.get_mount(mount).registry.list_objects():
                    target_key = self.build_key(self.default_mount, name)
                    self.save(target_key, mapping.load(mapping.build_key(mount, name)), on_conflict="overwrite")
            return

        if not isinstance(mapping, Mapping):
            raise TypeError("mapping must be a mapping or Store")

        for key, value in mapping.items():
            self[key] = value
