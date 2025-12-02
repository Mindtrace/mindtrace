from mindtrace.apps.inspectra.inspectra import InspectraService, ConfigSchema
from mindtrace.apps.inspectra.app.api.core.settings import settings

def main() -> None:
    config = ConfigSchema(
        name=settings.service_name,
        description=settings.service_description,
        version=settings.service_version,
        author=settings.service_author,
        author_email=settings.service_author_email,
        url=settings.service_url,
    )

    InspectraService.launch(
        "0.0.0.0:8000",
        block=True,
        config=config,
    )


if __name__ == "__main__":
    main()
