# crm_app/management/commands/seed_projects.py
from __future__ import annotations

import random
from datetime import timedelta
from typing import Optional

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import models, transaction
from django.utils import timezone
from django.utils.text import slugify


QC_HOSPITALS = [
    "CHUM (Centre hospitalier de l'Université de Montréal)",
    "CHU Sainte-Justine",
    "MUHC / CUSM (McGill University Health Centre)",
    "Hôpital général juif (Jewish General Hospital)",
    "Hôpital Maisonneuve-Rosemont",
    "Hôpital du Sacré-Cœur de Montréal",
    "Hôpital Notre-Dame",
    "Hôpital de Verdun",
    "Hôpital de LaSalle",
    "Hôpital du Lakeshore",
    "Hôpital Pierre-Boucher",
    "Hôpital Charles-Le Moyne",
    "Cité-de-la-Santé de Laval",
    "CHU de Québec – Hôpital de l'Enfant-Jésus",
    "CHU de Québec – Hôpital du Saint-Sacrement",
    "CHUS – Hôpital Fleurimont",
    "CHUS – Hôtel-Dieu de Sherbrooke",
    "CISSS de l’Outaouais – Hôpital de Gatineau",
    "CISSS de la Mauricie–Centre-du-Québec – Trois-Rivières",
    "CISSS de la Côte-Nord – Sept-Îles",
    "CISSS du Bas-Saint-Laurent – Rimouski",
    "CIUSSS du Saguenay–Lac-Saint-Jean – Chicoutimi",
    "CISSS de Chaudière-Appalaches – Lévis",
    "CISSS de Lanaudière – Joliette",
    "CISSS des Laurentides – Saint-Jérôme",
    "CISSS Montérégie-Centre – Anna-Laberge",
    "CISSS Montérégie-Est – Honoré-Mercier",
    "CISSS Montérégie-Ouest – Suroît",
]

FALLBACK_PRODUCTS = [
    "Dossier patient", "Planification blocs opératoires", "RIS/PACS",
    "Gestion des lits", "Portail cliniciens", "Portail patients",
    "Facturation", "Interfaçage HL7/FHIR", "BI/Analytique", "Pharmacie",
]


def pick_from_choices(field: models.Field, preferred: list[str] | None = None) -> Optional[str]:
    if not getattr(field, "choices", None):
        return None
    values = [value for value, _ in field.choices]
    if not values:
        return None
    if preferred:
        lowers = {str(v).lower(): v for v in values}
        for want in preferred:
            if want in values:
                return want
            if want.lower() in lowers:
                return lowers[want.lower()]
    return values[0]


def ensure_product_object(product_fk: models.ForeignKey) -> models.Model:
    ProductModel = product_fk.remote_field.model
    if ProductModel.objects.exists():
        return random.choice(list(ProductModel.objects.all()[:100]))

    # find a likely name field
    name_field = None
    for f in ProductModel._meta.fields:
        if isinstance(f, models.CharField) and f.name in ("name", "title", "label"):
            name_field = f.name
            break

    created = []
    if name_field:
        for nm in FALLBACK_PRODUCTS:
            try:
                created.append(ProductModel.objects.create(**{name_field: nm}))
            except Exception:
                pass
    else:
        # last resort
        try:
            created.append(ProductModel.objects.create())
        except Exception:
            # fill first char field we can
            cf = next((f for f in ProductModel._meta.fields if isinstance(f, models.CharField)), None)
            if cf:
                created.append(ProductModel.objects.create(**{cf.name: "Produit démo"}))

    return created[0] if created else ProductModel.objects.first()


def ensure_client_object(client_fk: models.ForeignKey) -> models.Model:
    ClientModel = client_fk.remote_field.model
    if ClientModel.objects.exists():
        return random.choice(list(ClientModel.objects.all()[:100]))

    # find a likely name field
    name_field = None
    for f in ClientModel._meta.fields:
        if isinstance(f, models.CharField) and f.name in ("name", "title", "label", "display_name"):
            name_field = f.name
            break

    if name_field:
        return ClientModel.objects.create(**{name_field: "Client démo"})
    try:
        return ClientModel.objects.create()
    except Exception:
        cf = next((f for f in ClientModel._meta.fields if isinstance(f, models.CharField)), None)
        if cf:
            return ClientModel.objects.create(**{cf.name: "Client démo"})
        raise RuntimeError("Impossible de créer un client de démonstration.")


def get_seed_user() -> models.Model:
    User = get_user_model()
    user = (User.objects.filter(is_superuser=True).first()
            or User.objects.filter(is_staff=True).first())
    if user:
        return user
    return User.objects.get_or_create(
        username="seed.bot",
        defaults={"email": "seed.bot@lgisolutions.com", "password": "unused-seed-password"},
    )[0]


def ensure_technician(tech_field: models.ForeignKey) -> models.Model:
    TechModel = tech_field.remote_field.model
    tech = TechModel.objects.first()
    if tech:
        return tech

    # Create a minimal Technician bound to a seed user
    user = get_seed_user()
    fields = {f.name: f for f in TechModel._meta.fields}
    kwargs = {}

    # user OneToOne/ForeignKey
    user_field_name = "user" if "user" in fields else None
    if user_field_name:
        kwargs[user_field_name] = user

    # optional fields commonly present
    if "role" in fields and isinstance(fields["role"], models.CharField):
        kwargs["role"] = "Spécialiste, déploiement des solutions"
    if "job_title" in fields and isinstance(fields["job_title"], models.CharField) and "role" not in kwargs:
        kwargs["job_title"] = "Spécialiste, déploiement des solutions"
    if "is_manager" in fields and isinstance(fields["is_manager"], models.BooleanField):
        kwargs["is_manager"] = False

    return TechModel.objects.create(**kwargs)


class Command(BaseCommand):
    help = "Create N demo projects with sequential project numbers like PRJ0034, PRJ0035, …"

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=25, help="How many projects to create.")
        parser.add_argument(
            "--start", type=int, default=34,
            help="Starting integer for PRJ#### (e.g. --start 34 -> PRJ0034)."
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        Project = apps.get_model("crm_app", "Project")
        proj_fields = {f.name: f for f in Project._meta.fields}

        # important fields
        project_number_field = "project_number" if "project_number" in proj_fields else None
        if not project_number_field:
            raise SystemExit("This command requires a 'project_number' field on Project.")

        # common fields (set only if present)
        title_field = "title" if "title" in proj_fields else ("name" if "name" in proj_fields else None)
        description_field = "description" if "description" in proj_fields else None
        start_field = "start_date" if "start_date" in proj_fields else ("date_start" if "date_start" in proj_fields else None)
        due_field = "due_date" if "due_date" in proj_fields else ("end_date" if "end_date" in proj_fields else None)
        budget_field = "budget" if "budget" in proj_fields else None
        progress_field = "progress" if "progress" in proj_fields else ("progress_percent" if "progress_percent" in proj_fields else None)
        created_by_field = "created_by" if "created_by" in proj_fields else None

        # enums / choices
        status_field = "status" if "status" in proj_fields else None
        status_value = pick_from_choices(proj_fields[status_field], ["IN_PROGRESS", "PLANNING", "ON_HOLD"]) if status_field else None
        phase_field = "phase" if "phase" in proj_fields else None
        phase_value = pick_from_choices(proj_fields[phase_field], ["PLANNING", "EXECUTION", "CLOSURE"]) if phase_field else None
        priority_field = "priority" if "priority" in proj_fields else None
        priority_value = pick_from_choices(proj_fields[priority_field], ["MEDIUM", "NORMAL", "HIGH"]) if priority_field else None

        environment_field = "environment" if "environment" in proj_fields else None

        # product can be FK or CharField
        product_field_name = "product" if "product" in proj_fields else None
        product_fk = proj_fields[product_field_name] if product_field_name and isinstance(proj_fields[product_field_name], models.ForeignKey) else None

        # client can be FK or CharField
        client_fk_field = None
        client_char_field = None
        for cand in ("client", "customer"):
            if cand in proj_fields:
                if isinstance(proj_fields[cand], models.ForeignKey):
                    client_fk_field = proj_fields[cand]
                elif isinstance(proj_fields[cand], (models.CharField, models.TextField)):
                    client_char_field = cand
                break
        if not client_fk_field and not client_char_field:
            # try name-like text field
            for cand in ("client_name", "customer_name", "hospital_name"):
                if cand in proj_fields and isinstance(proj_fields[cand], (models.CharField, models.TextField)):
                    client_char_field = cand
                    break

        # required technician FK?
        technician_field = "technician" if "technician" in proj_fields and isinstance(proj_fields["technician"], models.ForeignKey) else None

        self.stdout.write(self.style.NOTICE(f"Using Project={Project._meta.label}"))

        target_count = int(opts["count"])
        seq = int(opts["start"])
        created_count = 0
        used_titles = set()

        while created_count < target_count:
            prj_no = f"PRJ{seq:04d}"
            seq += 1

            if Project.objects.filter(**{project_number_field: prj_no}).exists():
                continue

            hospital = random.choice(QC_HOSPITALS)
            prod_name = random.choice(FALLBACK_PRODUCTS)
            title_value = f"{hospital} – Déploiement {prod_name}"
            if title_value in used_titles:
                continue
            used_titles.add(title_value)

            start = timezone.now().date() - timedelta(days=random.randint(10, 240))
            due = start + timedelta(days=random.randint(45, 180))

            data = {project_number_field: prj_no}

            if title_field:
                data[title_field] = title_value
            if description_field:
                data[description_field] = f"Déploiement du produit « {prod_name} » à {hospital}. (Données de démonstration)"

            if start_field:
                data[start_field] = start
            if due_field:
                data[due_field] = due

            if budget_field:
                data[budget_field] = random.randint(75_000, 1_200_000)
            if progress_field:
                data[progress_field] = random.randint(0, 100)

            if environment_field:
                env_val = pick_from_choices(proj_fields[environment_field], ["PROD", "TEST", "QA"])
                data[environment_field] = env_val or "TEST"

            if product_field_name:
                if product_fk:
                    data[product_field_name] = ensure_product_object(product_fk)
                else:
                    val = pick_from_choices(proj_fields[product_field_name], [prod_name]) or prod_name
                    data[product_field_name] = val

            if client_fk_field:
                data[client_fk_field.name] = ensure_client_object(client_fk_field)
            elif client_char_field:
                data[client_char_field] = hospital

            if "database_name" in proj_fields:
                base = f"db_{slugify(hospital)[:32]}"
                data["database_name"] = base or f"db_{prj_no.lower()}"
            if "db_server" in proj_fields:
                data["db_server"] = f"dbsrv-{random.randint(1,9)}.lgisolutions.local"
            if "app_server" in proj_fields:
                data["app_server"] = f"appsrv-{random.randint(1,9)}.lgisolutions.local"

            if created_by_field:
                data[created_by_field] = get_seed_user()

            if status_field and status_value is not None:
                data[status_field] = status_value
            if phase_field and phase_value is not None:
                data[phase_field] = phase_value
            if priority_field and priority_value is not None:
                data[priority_field] = priority_value

            if technician_field:
                data[technician_field] = ensure_technician(proj_fields[technician_field])

            Project.objects.create(**data)
            created_count += 1
            self.stdout.write(f" + {prj_no} · {title_value}")

        self.stdout.write(self.style.SUCCESS(f"Done. Created {created_count} projects."))
