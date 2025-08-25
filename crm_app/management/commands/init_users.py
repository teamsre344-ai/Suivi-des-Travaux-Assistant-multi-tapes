# crm_app/management/commands/init_users.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from random import choice, randint, random
from datetime import timedelta

from django.conf import settings
from crm_app.models import Technician, Project, ChecklistItem, TimelineEntry

DEFAULT_PASSWORD = "ChangeMe2025!"


class Command(BaseCommand):
    help = "Create demo users, technicians, and sample projects."

    def handle(self, *args, **kwargs):
        self.stdout.write("Seeding users/technicians from TEAM_DIRECTORY…")

        directory = getattr(settings, "TEAM_DIRECTORY", {})
        if not directory:
            self.stdout.write(self.style.WARNING("TEAM_DIRECTORY is not defined in settings."))
            return

        techs = []
        for email, data in directory.items():
            first = data.get("first_name", "")
            last = data.get("last_name", "")
            is_mgr = data.get("is_manager", False)
            role = data.get("role", "Technicien")

            username = email.split("@")[0].replace(".", "_").lower()
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "email": email,
                    "is_staff": bool(is_mgr),
                },
            )
            if created:
                user.set_password(DEFAULT_PASSWORD)
                user.save()

            tech, _ = Technician.objects.get_or_create(
                user=user,
                defaults={
                    "role": role,
                    "is_manager": is_mgr,
                    "phone": f"514-555-{randint(1000, 9999)}",
                },
            )
            
            if tech.is_manager != is_mgr or tech.role != role:
                tech.is_manager = is_mgr
                tech.role = role
                tech.save()

            techs.append(tech)

        self.stdout.write(self.style.SUCCESS(f"Created {len(techs)} technicians."))

        self.stdout.write("Creating sample projects…")

        # Keys must match your model choices exactly
        products = ["GRF", "GRM", "GFM", "Clinibase CI", "SIurge", "eClinibase", "BI"]
        work_types = ["Migration", "Mise a niveau", "Rehaussement", "Demenagement"]
        status_opts = ["pending", "in_progress", "completed"]
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

        for i in range(1, 16):
            tech = choice(techs)
            env = choice(envs)
            client = choice(clients)
            product = choice(products)
            status = choice(status_opts)

            pn = f"PRJ-{year}-{i:03d}"
            title = f"{'Test' if env == 'test' else 'Production'} — {client} — {product} — {pn}"

            # IMPORTANT: always provide SRE fields to satisfy the DB CHECK constraint
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
                work_type=choice(work_types),
                technician=tech,
                status=status,
                created_by=tech.user,
                sre_name="On-Call SRE",  # <- REQUIRED by chk_proj_prod_requires_sre
                sre_phone="514-555-0101",  # <- REQUIRED by chk_proj_prod_requires_sre
            )

            p, was_created = Project.objects.get_or_create(
                project_number=pn, defaults=defaults
            )

            # If project already exists (rerun), keep it intact (idempotent).
            if not was_created:
                continue

            # Populate checklist and timeline for new rows only
            checklist_labels = [
                "Demander les accès pour tous les serveurs",
                "Tester l'application (fonctionnement)",
                "Valider la version applicative, nom BD, établissement",
                "Valider l'heure début/fin du backup",
                "Valider FUSE",
                "Valider certificats",
                "Validation avec le client",
            ]
            p.checklist_data = {
                "items": [
                    {
                        "label": lbl,
                        "completed": (random() > 0.6) if status != "pending" else False,
                    }
                    for lbl in checklist_labels
                ]
            }
            p.save()

            for idx, label in enumerate(checklist_labels):
                ChecklistItem.objects.create(
                    project=p,
                    label=label,
                    order=idx,
                    completed=(random() > 0.6) if status != "pending" else False,
                )

            base = timezone.now() - timedelta(hours=randint(4, 48))
            events = [
                ("Connexion", 0),
                ("Début des travaux", 30),
                ("Backup", 60),
                ("Fin mise à niveau", 180),
            ]

            if status in ["in_progress", "completed"]:
                for label, minutes in events:
                    TimelineEntry.objects.create(
                        project=p,
                        environment=env,
                        event_label=label,
                        event_time=base + timedelta(minutes=minutes),
                    )
                if status == "completed":
                    TimelineEntry.objects.create(
                        project=p,
                        environment=env,
                        event_label="Clôture",
                        event_time=base + timedelta(minutes=240),
                    )

            created_count += 1

        self.stdout.write(self.style.SUCCESS(f"Created {created_count} projects."))
        self.stdout.write(
            self.style.SUCCESS(f"Default password for all users: {DEFAULT_PASSWORD}")
        )
