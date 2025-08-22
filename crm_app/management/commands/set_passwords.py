from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = "Sets the password for all users to a default value"

    def handle(self, *args, **options):
        for user in User.objects.all():
            user.set_password("deploiement")
            user.save()
        self.stdout.write(self.style.SUCCESS("Successfully set password for all users"))
