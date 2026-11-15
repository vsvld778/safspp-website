"""Permissions for public collected assets, independent of private file storage."""
from django.contrib.staticfiles.storage import StaticFilesStorage


class PublicStaticFilesStorage(StaticFilesStorage):
    def __init__(self, *args, **kwargs):
        kwargs["file_permissions_mode"] = 0o644
        kwargs["directory_permissions_mode"] = 0o755
        super().__init__(*args, **kwargs)
