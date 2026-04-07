"""Example usage of declarative Mount definitions with Registry and Store.

This sample shows three things:

1. building a ``Registry`` from a declarative ``Mount``
2. building a ``Store`` from multiple mounts
3. saving/loading through qualified and unqualified Store keys

The sample only uses local mounts so it can run without cloud credentials.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from mindtrace.registry import LocalMountConfig, Mount, Registry, Store


def main() -> None:
    with TemporaryDirectory(prefix="mindtrace-sample-a-") as dir_a, TemporaryDirectory(
        prefix="mindtrace-sample-b-"
    ) as dir_b:
        primary_mount = Mount(
            name="primary",
            backend="local",
            config=LocalMountConfig(uri=dir_a),
            is_default=True,
            registry_options={
                "version_objects": True,
                "mutable": True,
            },
        )

        registry = Registry.from_mount(primary_mount)
        registry.save("sample:direct", {"hello": "registry-from-mount"})
        print("Registry.from_mount ->", registry.load("sample:direct"))

        archive_mount = Mount(
            name="archive",
            backend="local",
            config=LocalMountConfig(uri=dir_b),
            read_only=False,
            registry_options={
                "version_objects": True,
                "mutable": True,
            },
        )

        store = Store.from_mounts([primary_mount, archive_mount])

        print("Configured mounts:", store.list_mounts())
        print("Default mount:", store.default_mount)
        print("Mount info:")
        for name, info in store.list_mount_info().items():
            print(f"  - {name}: {info['backend']}")

        store.save("sample:item", {"saved_to": "default_mount"})
        print("Unqualified load ->", store.load("sample:item"))
        print("Qualified load ->", store.load("primary/sample:item"))

        store.save("archive/sample:item", {"saved_to": "archive_mount"})
        print("Archive qualified load ->", store.load("archive/sample:item"))

        print("Objects by mount:")
        for key in sorted(store.list_objects()):
            print(f"  - {key}")

        derived_mount = registry.mount
        print("Derived mount from registry:")
        print(
            {
                "name": derived_mount.name,
                "backend": str(derived_mount.backend),
                "uri": derived_mount.display_uri(),
            }
        )

        reconstructed = Mount.from_registry(registry)
        print("Reconstructed mount backend ->", reconstructed.backend)

        extra_store = Store()
        extra_store.add_mount(registry)
        print("Derived mount names from Registry ->", extra_store.list_mounts())

        print("Primary dir:", Path(dir_a))
        print("Archive dir:", Path(dir_b))


if __name__ == "__main__":
    main()
