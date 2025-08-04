from mindtrace.storage import GCSStorageHandler
from poseidon.backend.core.config import settings

gcs_storage_handler = GCSStorageHandler(
    bucket_name=settings.GCP_BUCKET_NAME,
    credentials_path=settings.GCP_CREDENTIALS_PATH,
)



def presign_url(path: str) -> str:
    return gcs_storage_handler.get_presigned_url(path)
