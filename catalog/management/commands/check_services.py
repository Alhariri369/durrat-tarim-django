"""Management command to verify database, migrations, static assets, and ImageKit."""

from __future__ import annotations

import uuid
from io import BytesIO
from pathlib import Path

import requests
from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connection
from django.db.migrations.executor import MigrationExecutor
from PIL import Image

from catalog.imagekit_storage import FILES_ENDPOINT, ImageKitStorage

REQUIRED_STATIC_FILES = (
    "css/output.css",
    "images/product-placeholder.svg",
)


def _build_healthcheck_png() -> ContentFile:
    """Create a tiny valid 100x100 PNG in memory for storage write verification."""
    buffer = BytesIO()
    img = Image.new("RGB", (100, 100), color=(212, 175, 55))
    img.save(buffer, format="PNG")
    buffer.seek(0)
    content = ContentFile(buffer.getvalue(), name=f"healthcheck_{uuid.uuid4().hex}.png")
    content.content_type = "image/png"
    return content


class Command(BaseCommand):
    help = (
        "Verify service health: database connectivity, applied migrations, "
        "required static assets, and optional ImageKit/storage checks."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--check-imagekit",
            action="store_true",
            help="Verify ImageKit configuration and API authentication safely.",
        )
        parser.add_argument(
            "--write-test",
            action="store_true",
            help=(
                "Upload a tiny Pillow PNG via storage and immediately delete it "
                "to verify end-to-end write/delete permissions."
            ),
        )
        parser.add_argument(
            "--timeout",
            type=float,
            default=15.0,
            help="HTTP timeout in seconds for external API checks (default: 15).",
        )

    def handle(self, *args, **options):
        failures: list[str] = []

        self._check_database(failures)
        self._check_migrations(failures)
        self._check_static_files(failures)

        check_imagekit = options["check_imagekit"]
        write_test = options["write_test"]
        timeout = options["timeout"]

        if check_imagekit:
            self._check_imagekit(failures, timeout=timeout)

        if write_test:
            self._check_storage_write(failures, use_imagekit=check_imagekit)

        if failures:
            summary = "\n".join(f" - {msg}" for msg in failures)
            raise CommandError(
                f"Service health checks failed ({len(failures)} error(s)):\n{summary}"
            )

        self.stdout.write(self.style.SUCCESS("All requested service checks passed."))

    def _ok(self, label: str, detail: str) -> None:
        self.stdout.write(self.style.SUCCESS(f"[OK] {label}: {detail}"))

    def _fail(self, failures: list[str], label: str, detail: str) -> None:
        message = f"{label}: {detail}"
        failures.append(message)
        self.stderr.write(self.style.ERROR(f"[FAIL] {message}"))

    def _check_database(self, failures: list[str]) -> None:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                row = cursor.fetchone()
            if not row or row[0] != 1:
                self._fail(
                    failures,
                    "database",
                    f"Unexpected SELECT 1 response: {row!r}",
                )
                return
            vendor = connection.vendor
            self._ok("database", f"Connected ({vendor})")
        except (DatabaseError, OSError) as exc:
            self._fail(
                failures,
                "database",
                f"Connection failed ({type(exc).__name__}: {exc})",
            )

    def _check_migrations(self, failures: list[str]) -> None:
        try:
            executor = MigrationExecutor(connection)
            targets = executor.loader.graph.leaf_nodes()
            plan = executor.migration_plan(targets)
            if plan:
                pending = ", ".join(
                    f"{migration.app_label}.{migration.name}"
                    for migration, _ in plan
                )
                self._fail(
                    failures,
                    "migrations",
                    f"{len(plan)} unapplied migration(s): {pending}",
                )
                return
            self._ok("migrations", "All migrations applied")
        except (DatabaseError, OSError) as exc:
            self._fail(
                failures,
                "migrations",
                f"Migration check failed ({type(exc).__name__}: {exc})",
            )

    def _check_static_files(self, failures: list[str]) -> None:
        static_root = getattr(settings, "STATIC_ROOT", None)
        static_root_path = Path(static_root) if static_root else None

        for rel_path in REQUIRED_STATIC_FILES:
            found_location: str | None = None
            if static_root_path is not None:
                candidate = static_root_path / rel_path
                if candidate.is_file():
                    found_location = str(candidate)

            if found_location is None:
                located = finders.find(rel_path)
                if located:
                    found_location = str(located)

            if found_location:
                self._ok(f"static:{rel_path}", f"Found ({found_location})")
            else:
                self._fail(
                    failures,
                    f"static:{rel_path}",
                    "Not found in STATIC_ROOT or staticfiles finders",
                )

    def _check_imagekit(self, failures: list[str], timeout: float) -> None:
        private_key = getattr(settings, "IMAGEKIT_PRIVATE_KEY", "") or ""
        url_endpoint = getattr(settings, "IMAGEKIT_URL_ENDPOINT", "") or ""

        if not private_key:
            self._fail(failures, "imagekit", "IMAGEKIT_PRIVATE_KEY is not configured")
            return
        if private_key != private_key.strip():
            self._fail(
                failures,
                "imagekit",
                "IMAGEKIT_PRIVATE_KEY contains leading or trailing whitespace",
            )
            return
        if not url_endpoint:
            self._fail(failures, "imagekit", "IMAGEKIT_URL_ENDPOINT is not configured")
            return
        if not url_endpoint.startswith(("https://", "http://")):
            self._fail(
                failures,
                "imagekit",
                "IMAGEKIT_URL_ENDPOINT must start with https:// or http://",
            )
            return

        try:
            response = requests.get(
                FILES_ENDPOINT,
                params={"limit": 1},
                auth=(private_key, ""),
                timeout=timeout,
            )
        except requests.RequestException as exc:
            self._fail(
                failures,
                "imagekit",
                f"API request failed ({type(exc).__name__})",
            )
            return

        if response.status_code != 200:
            snippet = (response.text or "").strip().replace("\n", " ")[:200]
            self._fail(
                failures,
                "imagekit",
                f"API returned HTTP {response.status_code} ({snippet})",
            )
            return

        self._ok(
            "imagekit",
            f"Authenticated successfully (endpoint={url_endpoint.rstrip('/')})",
        )

    def _check_storage_write(
        self, failures: list[str], use_imagekit: bool = False
    ) -> None:
        storage = ImageKitStorage() if use_imagekit else default_storage
        storage_label = type(storage).__name__

        if use_imagekit and (
            not getattr(storage, "private_key", "")
            or not getattr(storage, "url_endpoint", "")
        ):
            self._fail(
                failures,
                "storage-write",
                "Cannot run ImageKit write test without credentials configured",
            )
            return

        probe_file = _build_healthcheck_png()
        target_name = f"_healthcheck/{probe_file.name}"
        saved_name: str | None = None

        try:
            saved_name = storage.save(target_name, probe_file)
            self._ok("storage-write", f"Uploaded probe via {storage_label} ({saved_name})")
        except (OSError, requests.RequestException, RuntimeError, ValueError) as exc:
            self._fail(
                failures,
                "storage-write",
                f"Upload failed via {storage_label} ({type(exc).__name__}: {exc})",
            )
            return
        finally:
            if saved_name:
                try:
                    storage.delete(saved_name)
                    self._ok(
                        "storage-cleanup",
                        f"Deleted probe via {storage_label} ({saved_name})",
                    )
                except (
                    OSError,
                    requests.RequestException,
                    RuntimeError,
                    ValueError,
                ) as exc:
                    self._fail(
                        failures,
                        "storage-cleanup",
                        f"Delete failed for {saved_name} ({type(exc).__name__}: {exc})",
                    )
