import re
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured


def database_config(env):
    config = env.db("DATABASE_URL")
    if config["ENGINE"] != "django.db.backends.postgresql":
        raise ImproperlyConfigured("This service requires PostgreSQL.")
    config["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
    config["CONN_HEALTH_CHECKS"] = True
    options = config.setdefault("OPTIONS", {})
    options["connect_timeout"] = 10
    schema = env("DB_SCHEMA", default="public")
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", schema):
        raise ImproperlyConfigured("DB_SCHEMA must be a lowercase PostgreSQL identifier.")
    if schema != "public":
        options["options"] = f"-c search_path={schema},public,extensions -c statement_timeout=30000"
    if env("DB_SSLMODE", default=""):
        options["sslmode"] = env("DB_SSLMODE")
    if env("DB_SSLROOTCERT", default=""):
        options["sslrootcert"] = env("DB_SSLROOTCERT")
    if env.bool("DB_TRANSACTION_POOLER", default=False):
        config["DISABLE_SERVER_SIDE_CURSORS"] = True
        options["prepare_threshold"] = None
        config["CONN_MAX_AGE"] = 0
    return config


def media_storage_config(env):
    backend = env("MEDIA_STORAGE", default="local")
    if backend == "local":
        return {"BACKEND": "django.core.files.storage.FileSystemStorage"}
    if backend != "supabase":
        raise ImproperlyConfigured("MEDIA_STORAGE must be local or supabase.")
    endpoint = env("SUPABASE_S3_ENDPOINT")
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
    ):
        raise ImproperlyConfigured(
            "SUPABASE_S3_ENDPOINT must be an HTTPS endpoint without credentials."
        )
    from botocore.config import Config

    required = {
        key: env(key)
        for key in [
            "SUPABASE_S3_REGION",
            "SUPABASE_S3_ACCESS_KEY_ID",
            "SUPABASE_S3_SECRET_ACCESS_KEY",
            "SUPABASE_STORAGE_BUCKET",
        ]
    }
    if any(not value.strip() for value in required.values()):
        raise ImproperlyConfigured("All Supabase S3 settings must be nonempty.")
    return {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "endpoint_url": endpoint,
            "region_name": required["SUPABASE_S3_REGION"],
            "access_key": required["SUPABASE_S3_ACCESS_KEY_ID"],
            "secret_key": required["SUPABASE_S3_SECRET_ACCESS_KEY"],
            "bucket_name": required["SUPABASE_STORAGE_BUCKET"],
            "default_acl": None,
            "file_overwrite": False,
            "querystring_auth": True,
            "querystring_expire": 60,
            "max_memory_size": 2 * 1024 * 1024,
            "object_parameters": {"CacheControl": "private, no-store"},
            "client_config": Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                connect_timeout=10,
                read_timeout=30,
                retries={"max_attempts": 2},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        },
    }
