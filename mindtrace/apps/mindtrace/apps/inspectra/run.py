from mindtrace.apps.inspectra.inspectra import InspectraService, ConfigSchema


def main() -> None:
    # TODO: Change these config values to load from environment or config file
    config = ConfigSchema(
        name="inspectra",
        description="Inspectra Platform",
        version="1.0.0",
        author="Inspectra",
        author_email="inspectra@inspectra.com",
        url="https://inspectra.com",
    )

    # Launch the service via the Mindtrace Service framework
    InspectraService.launch(
        "0.0.0.0:8000",
        block=True,
        config=config,
    )


if __name__ == "__main__":
    main()