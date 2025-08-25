from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from random import choice, randint, random
from datetime import timedelta

from crm_app.models import Technician, Project, ChecklistItem, TimelineEntry

class Command(BaseCommand):
    help = "Create 24 cancelled and 30 late projects."

    def handle(self, *args, **kwargs):
        self.stdout.write("Seeding 24 cancelled and 30 late projects…")

        try:
            creator = User.objects.get(email__iexact="patrick.savard@lgisolutions.com")
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR("User patrick.savard@lgisolutions.com not found."))
            return

        specialists = list(Technician.objects.filter(is_manager=False))
        if not specialists:
            self.stdout.write(self.style.ERROR("No specialists found."))
            return

        products = ["GRF", "GRM", "GFM", "Clinibase CI", "SIurge", "eClinibase"]
        work_types = ["Migration", "Mise a niveau", "Rehaussement", "Demenagement"]
        envs = ["test", "prod"]
        clients = [
            "CISSS Laval",
            "CIUSSS MCQ",
            "CHU Québec",
            "CISSS Montérégie",
            "CIUSSS EMTL",
        ]

        year = timezone.now().year
        created_count = 0
        
        last_project = Project.objects.order_by('-project_number').first()
        last_project_number = 0
        if last_project:
            try:
                last_project_number = int(last_project.project_number.split('-')[-1])
            except (ValueError, IndexError):
                pass

        # Create 24 cancelled projects
        for i in range(1, 25):
            tech = choice(specialists)
            env = choice(envs)
            client = choice(clients)
            product = choice(products)
            work_type = choice(work_types)

            pn = f"PRJ-{year}-{last_project_number + i:03d}"
            title = f"{'Test' if env == 'test' else 'Production'} — {client} — {product} — {pn}"

            defaults = dict(
                title=title,
                environment=env,
                client_name=client,
                product=product,
                database_name=f"DB_{client.split()[0].upper()}",
                db_server=f"srv-db-{randint(1, 5):02d}",
                app_server=f"srv-app-{randint(1, 5):02d}",
                fuse_validation="OK" if random() > 0.3 else "NOK",
                certificate_validation="OK" if random() > 0.2 else "NOK",
                work_type=work_type,
                technician=tech,
                status="cancelled",
                created_by=creator,
                sre_name="On-Call SRE",
                sre_phone="514-555-0101",
            )

            p, was_created = Project.objects.get_or_create(
                project_number=pn, defaults=defaults
            )

            if not was_created:
                continue

            created_count += 1
            
        last_project_number += 24

        # Create 30 late projects
        for i in range(1, 31):
            tech = choice(specialists)
            env = choice(envs)
            client = choice(clients)
            product = choice(products)
            work_type = choice(work_types)

            pn = f"PRJ-{year}-{last_project_number + i:03d}"
            title = f"{'Test' if env == 'test' else 'Production'} — {client} — {product} — {pn}"

            defaults = dict(
                title=title,
                environment=env,
                client_name=client,
                product=product,
                database_name=f"DB_{client.split()[0].upper()}",
                db_server=f"srv-db-{randint(1, 5):02d}",
                app_server=f"srv-app-{randint(1, 5):02d}",
                fuse_validation="OK" if random() > 0.3 else "NOK",
                certificate_validation="OK" if random() > 0.2 else "NOK",
                work_type=work_type,
                technician=tech,
                status="completed",
                created_by=creator,
                sre_name="On-Call SRE",
                sre_phone="514-555-0101",
                date=timezone.now() - timedelta(days=randint(1, 30)),
                updated_at=timezone.now(),
            )

            p, was_created = Project.objects.get_or_create(
                project_number=pn, defaults=defaults
            )

            if not was_created:
                continue

            created_count += 1

        self.stdout.write(self.style.SUCCESS(f"Created {created_count} projects."))
