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
        # A declarative mount can be used to build a single Registry.
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

        # A Store can be built from multiple declarative mounts.
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

        # Unqualified saves go to the default mount.
        store.save("sample:item", {"saved_to": "default_mount"})
        print("Unqualified load ->", store.load("sample:item"))
        print("Qualified load ->", store.load("primary/sample:item"))

        # Qualified saves can target a specific mount.
        store.save("archive/sample:item", {"saved_to": "archive_mount"})
        print("Archive qualified load ->", store.load("archive/sample:item"))

        # If the same unqualified object exists in multiple mounts, be explicit.
        print("Objects by mount:")
        for key in sorted(store.list_objects()):
            print(f"  - {key}")

        # You can also derive a best-effort declarative Mount from an existing Registry.
        derived_mount = registry.mount
        print("Derived mount from registry:")
        print(
            {
                "name": derived_mount.name,
                "backend": str(derived_mount.backend),
                "uri": derived_mount.display_uri(),
            }
        )

        # And reconstruct a mount directly from a Registry instance.
        reconstructed = Mount(registry)
        print("Reconstructed mount backend ->", reconstructed.backend)

        # Show the underlying directories just so it's obvious where data landed.
        print("Primary dir:", Path(dir_a))
        print("Archive dir:", Path(dir_b))


if __name__ == "__main__":
    main()
