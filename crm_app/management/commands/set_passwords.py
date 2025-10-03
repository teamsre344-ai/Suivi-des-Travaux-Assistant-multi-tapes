from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = "Sets the password for a specific user or all users to a default value"

    def add_arguments(self, parser):
        parser.add_argument(
            "email",
            nargs="?",
            type=str,
            help="Email of the user to set the password for. If not provided, sets password for all users.",
        )
        parser.add_argument(
            "password",
            nargs="?",
            type=str,
            default="deploiement",
            help="The password to set. Defaults to 'deploiement'.",
        )

    def handle(self, *args, **options):
        email = options["email"]
        password = options["password"]

        if email:
            try:
                user = User.objects.get(email=email)
                user.set_password(password)
                user.save()
                self.stdout.write(self.style.SUCCESS(f"Successfully set password for user {email}"))
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"User with email {email} not found."))
        else:
            for user in User.objects.all():
                user.set_password(password)
                user.save()
            self.stdout.write(self.style.SUCCESS(f"Successfully set password for all users to '{password}'"))
