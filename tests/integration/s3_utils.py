"""Raw boto3 helpers for S3 integration-test setup, teardown and assertions.

Fixtures use these rather than ``S3StorageHandler`` / ``S3RegistryBackend`` so that bucket
bookkeeping and verification stay independent of the code under test.
"""

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import ClientError


def make_s3_client(endpoint: str, access_key: str, secret_key: str, secure: bool) -> BaseClient:
    """Build a boto3 S3 client configured the same way as ``S3StorageHandler``.

    Args:
        endpoint: ``host:port`` of the S3-compatible service.
        access_key: Access key ID.
        secret_key: Secret access key.
        secure: Whether to connect over HTTPS.

    Returns:
        A boto3 S3 client.
    """
    return boto3.client(
        "s3",
        endpoint_url=f"{'https' if secure else 'http'}://{endpoint}",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="us-east-1",
        config=Config(signature_version="s3v4"),
    )


def bucket_exists(client: BaseClient, bucket: str) -> bool:
    """Return whether ``bucket`` exists.

    Args:
        client: boto3 S3 client.
        bucket: Bucket name.

    Returns:
        True if the bucket exists, False if the service reports it missing.
    """
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchBucket"):
            return False
        raise
    return True


def list_keys(client: BaseClient, bucket: str, prefix: str = "") -> list[str]:
    """Return the keys of all objects under ``prefix``, recursively.

    Args:
        client: boto3 S3 client.
        bucket: Bucket name.
        prefix: Key prefix to list under.

    Returns:
        Object keys, without directory-like common prefixes.
    """
    paginator = client.get_paginator("list_objects_v2")
    return [obj["Key"] for page in paginator.paginate(Bucket=bucket, Prefix=prefix) for obj in page.get("Contents", [])]


def delete_keys(client: BaseClient, bucket: str, prefix: str = "") -> None:
    """Delete all objects under ``prefix``.

    Args:
        client: boto3 S3 client.
        bucket: Bucket name.
        prefix: Key prefix to delete under.
    """
    for key in list_keys(client, bucket, prefix):
        client.delete_object(Bucket=bucket, Key=key)


def delete_bucket(client: BaseClient, bucket: str) -> None:
    """Delete ``bucket`` along with all of its objects.

    Args:
        client: boto3 S3 client.
        bucket: Bucket name.
    """
    delete_keys(client, bucket)
    client.delete_bucket(Bucket=bucket)
