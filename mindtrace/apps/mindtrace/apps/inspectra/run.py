from mindtrace.apps.inspectra.inspectra import InspectraService, ConfigSchema
from mindtrace.apps.inspectra.core.settings import settings


def main() -> None:
    config = ConfigSchema(
        name=settings.service_name,
        description=settings.service_description,
        version=settings.service_version,
        author=settings.service_author,
        author_email=settings.service_author_email,
        url=settings.service_url,  # public URL
    )

    bind_url = f"http://0.0.0.0:{settings.api_port}"

    print(f"Starting Inspectra service at {settings.service_url} (bind: {bind_url})...")
    print("Press Ctrl+C to stop.")

    InspectraService.launch(
        url=bind_url,
        block=True,
        config=config.model_dump(),
    )


if __name__ == "__main__":
    main()