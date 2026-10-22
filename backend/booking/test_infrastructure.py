import os
from unittest.mock import patch

import environ
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.infrastructure import database_config, media_storage_config


class InfrastructureTests(SimpleTestCase):
    def test_postgres_schema_ssl_and_transaction_pooler_options(self):
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://test:placeholder@localhost/test",
                "DB_SCHEMA": "tynys",
                "DB_SSLMODE": "verify-full",
                "DB_SSLROOTCERT": "/run/secrets/ca.pem",
                "DB_TRANSACTION_POOLER": "True",
            },
            clear=True,
        ):
            result = database_config(environ.Env())
        self.assertEqual(result["OPTIONS"]["sslmode"], "verify-full")
        self.assertEqual(result["OPTIONS"]["sslrootcert"], "/run/secrets/ca.pem")
        self.assertIn("search_path=tynys,public,extensions", result["OPTIONS"]["options"])
        self.assertTrue(result["DISABLE_SERVER_SIDE_CURSORS"])
        self.assertIsNone(result["OPTIONS"]["prepare_threshold"])
        self.assertEqual(result["CONN_MAX_AGE"], 0)

    def test_database_rejects_sqlite_and_invalid_schema(self):
        for values in [
            {"DATABASE_URL": "sqlite:////tmp/unused.db"},
            {"DATABASE_URL": "postgresql://localhost/test", "DB_SCHEMA": "bad,public"},
        ]:
            with self.subTest(values=values), patch.dict(os.environ, values, clear=True):
                with self.assertRaises(ImproperlyConfigured):
                    database_config(environ.Env())

    def test_private_supabase_storage_options_and_fail_closed_config(self):
        values = {
            "MEDIA_STORAGE": "supabase",
            "SUPABASE_S3_ENDPOINT": "https://example.storage.supabase.co/storage/v1/s3",
            "SUPABASE_S3_REGION": "example-region",
            "SUPABASE_S3_ACCESS_KEY_ID": "unit-test-placeholder",
            "SUPABASE_S3_SECRET_ACCESS_KEY": "unit-test-placeholder",
            "SUPABASE_STORAGE_BUCKET": "private-test",
        }
        with patch.dict(os.environ, values, clear=True):
            result = media_storage_config(environ.Env())["OPTIONS"]
            self.assertIsNone(result["default_acl"])
            self.assertTrue(result["querystring_auth"])
            self.assertEqual(result["querystring_expire"], 60)
            self.assertEqual(result["client_config"].s3["addressing_style"], "path")
            self.assertEqual(result["object_parameters"]["CacheControl"], "private, no-store")
            os.environ["SUPABASE_S3_SECRET_ACCESS_KEY"] = ""
            with self.assertRaises(ImproperlyConfigured):
                media_storage_config(environ.Env())
            os.environ["SUPABASE_S3_ENDPOINT"] = "http://insecure.example"
            with self.assertRaises(ImproperlyConfigured):
                media_storage_config(environ.Env())
