import getpass
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

class Command(BaseCommand):
    help = "Create a coordinator with a hidden interactive password; no password in arguments/logs."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--name", required=True)

    def handle(self, *args, **options):
        User = get_user_model()
        email = options["email"].strip().casefold()
        if User.objects.filter(email__iexact=email).exists():
            raise CommandError("User already exists; this command does not change credentials or permissions.")
        password = getpass.getpass("New coordinator password: ")
        confirmation = getpass.getpass("Confirm password: ")
        if password != confirmation:
            raise CommandError("Passwords do not match.")
        candidate = User(email=email, display_name=options["name"])
        try:
            validate_password(password, candidate)
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages)) from exc
        with transaction.atomic():
            group, _ = Group.objects.get_or_create(name="Координатор фонда")
            codenames = ["view_supportcase", "change_supportcase", "view_casemessage", "add_casemessage", "view_caseevent", "view_organization"]
            group.permissions.set(Permission.objects.filter(content_type__app_label="portal", codename__in=codenames))
            user = User.objects.create_user(email=email, password=password, display_name=options["name"], is_staff=True)
            user.groups.add(group)
        self.stdout.write(self.style.SUCCESS("Coordinator account created. Password was not printed."))
