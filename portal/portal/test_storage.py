import os
import stat
from pathlib import Path
from tempfile import TemporaryDirectory
from django.core.files.storage import storages
from django.core.management import call_command
from django.test import SimpleTestCase, override_settings


class StaticStoragePermissionTests(SimpleTestCase):
    def test_collectstatic_creates_nginx_readable_assets_under_restrictive_umask(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            (source / "organization").mkdir(parents=True)
            (source / "organization" / "app.js").write_text("/* public test asset */")
            destination = root / "collected"
            with override_settings(STATIC_ROOT=destination, STATICFILES_DIRS=[source],
                    STATICFILES_FINDERS=["django.contrib.staticfiles.finders.FileSystemFinder"]):
                previous_umask = os.umask(0o027)
                try:
                    call_command("collectstatic", interactive=False, verbosity=0)
                finally:
                    os.umask(previous_umask)
            for path in (destination, destination / "organization"):
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o755)
            self.assertEqual(stat.S_IMODE((destination / "organization" / "app.js").stat().st_mode), 0o644)

    @override_settings(FILE_UPLOAD_PERMISSIONS=0o600, FILE_UPLOAD_DIRECTORY_PERMISSIONS=0o700)
    def test_private_file_storage_keeps_its_own_permissions(self):
        self.assertEqual(storages["default"].file_permissions_mode, 0o600)
        self.assertEqual(storages["default"].directory_permissions_mode, 0o700)
        self.assertEqual(storages["staticfiles"].file_permissions_mode, 0o644)
        self.assertEqual(storages["staticfiles"].directory_permissions_mode, 0o755)
