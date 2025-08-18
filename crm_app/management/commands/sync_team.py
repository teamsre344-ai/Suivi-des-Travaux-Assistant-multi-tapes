# crm_app/management/commands/sync_team.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Tuple, Optional

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction
from django.utils.text import slugify

from crm_app.models import Technician


@dataclass
class Person:
    first_name: str
    last_name: str
    email: str
    role: str
    is_manager: bool = False

    @property
    def localpart(self) -> str:
        return self.email.split("@", 1)[0].lower()

    def legacy_email(self, old_domain: str = "logibe.com") -> str:
        return f"{self.localpart}@{old_domain}".lower()


# === Canonical team list (exact titles from your org picture; Patrick added as manager) ===
TEAM: Tuple[Person, ...] = (
    Person("Mahmoud", "Feki", "mahmoud.feki@lgisolutions.com", "Spécialiste principal, déploiement"),
    Person("Ruben", "Geghamyan", "ruben.geghamyan@lgisolutions.com", "Spécialiste principal, déploiement"),
    Person("Eric", "Lamontagne", "eric.lamontagne@lgisolutions.com", "Spécialiste principal, déploiement"),
    Person("Frédéric", "Rousseau", "frederic.rousseau@lgisolutions.com", "Spécialiste principal, déploiement"),
    Person("Éric", "Champagne", "eric.champagne@lgisolutions.com", "Spécialiste principal, déploiement"),
    Person("Marc", "Banville", "marc.banville@lgisolutions.com", "Spécialiste principal, déploiement"),
    Person("Halimatou", "Ly", "halimatou.ly@lgisolutions.com", "Spécialiste principal, déploiement"),
    Person("Roméo", "Kutnjem", "romeo.kutnjem@lgisolutions.com", "Spécialiste, déploiement des solutions"),
    Person("Sylvain", "Berthiaume", "sylvain.berthiaume@lgisolutions.com", "Spécialiste principal, déploiement"),
    Person("Masamba", "Lema", "masamba.lema@lgisolutions.com", "Spécialiste principal, déploiement"),
    Person("Taoufik", "Toughrai", "taoufik.toughrai@lgisolutions.com", "Spécialiste, déploiement des solutions"),
    Person("Mambibe Frank", "Merari", "frank.binde@lgisolutions.com", "Spécialiste, déploiement des solutions"),
    Person("Dounia", "ElBaine", "dounia.elbaine@lgisolutions.com", "Conseiller en planification"),
    Person("Ann-Pier", "Lucas-Mercier", "ann-pier.lucas-mercier@lgisolutions.com", "Conseiller en planification"),
    Person("Jessyca", "Lantagne", "jessyca.lantagne@lgisolutions.com", "Conseiller en planification"),
    Person("Pierre Ernest", "Veillard", "pierre.veillard@lgisolutions.com", "Spécialiste principal, déploiement"),
    # Manager
    Person(
        "Patrick",
        "Savard",
        "patrick.savard@lgisolutions.com",
        "Gestionnaire d’équipe, déploiement (600-IFS – Services gérés)",
        is_manager=True,
    ),
)


def find_user_by_emails(new_email: str, legacy_email: str) -> Optional[User]:
    # Try exact new email first, then legacy
    u = User.objects.filter(email__iexact=new_email).first()
    if u:
        return u
    return User.objects.filter(email__iexact=legacy_email).first()


def unique_username(base: str) -> str:
    """
    Ensure username uniqueness. Start from base, then base-2, base-3, ...
    """
    base = base.lower().replace("@", "_at_")
    candidate = base
    i = 2
    while User.objects.filter(username__iexact=candidate).exists():
        candidate = f"{base}-{i}"
        i += 1
    return candidate


class Command(BaseCommand):
    help = (
        "Sync users to the official team list:\n"
        " - migrate emails from @logibe.com -> @lgisolutions.com (same local part)\n"
        " - create/update Users (first/last/email)\n"
        " - create/update Technician(role, is_manager)\n"
        "Run without flags for a DRY-RUN preview. Add --commit to apply.\n"
        "Optionally --deactivate-missing to set is_active=False for users not in the list."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Actually write changes to the database (default is dry-run).",
        )
        parser.add_argument(
            "--deactivate-missing",
            action="store_true",
            help="Deactivate users with @lgisolutions.com or @logibe.com not present in TEAM.",
        )

    def handle(self, *args, **opts):
        commit = opts["commit"]
        deactivate_missing = opts["deactivate_missing"]

        actions = []
        warnings = []

        team_by_new_email: Dict[str, Person] = {p.email.lower(): p for p in TEAM}
        new_emails = set(team_by_new_email.keys())
        legacy_emails = {p.legacy_email() for p in TEAM}

        # --- Upsert all listed people ---
        for p in TEAM:
            new_email = p.email.lower()
            legacy_email = p.legacy_email()

            u = find_user_by_emails(new_email, legacy_email)

            if u is None:
                # create user
                username_base = p.localpart
                username = unique_username(username_base)
                actions.append(f"CREATE User(username={username}, email={new_email})")
                if commit:
                    u = User(username=username, email=new_email, first_name=p.first_name, last_name=p.last_name)
                    u.set_unusable_password()  # passwordless / allowlist flow
                    u.is_active = True
                    u.save()
            else:
                # update user
                need_update = []
                if u.email.lower() != new_email:
                    need_update.append(f"email: {u.email} -> {new_email}")
                if u.first_name != p.first_name:
                    need_update.append(f"first_name: {u.first_name} -> {p.first_name}")
                if u.last_name != p.last_name:
                    need_update.append(f"last_name: {u.last_name} -> {p.last_name}")

                if need_update:
                    actions.append(f"UPDATE User({u.username}): " + "; ".join(need_update))
                    if commit:
                        u.email = new_email
                        u.first_name = p.first_name
                        u.last_name = p.last_name
                        u.is_active = True
                        u.save()

            if commit:
                # ensure Technician row
                tech, _ = Technician.objects.get_or_create(user=u, defaults={"role": p.role})
                updates = []
                if tech.role != p.role:
                    updates.append(f"role: {tech.role} -> {p.role}")
                    tech.role = p.role
                if getattr(tech, "is_manager", False) != p.is_manager:
                    updates.append(f"is_manager: {getattr(tech, 'is_manager', False)} -> {p.is_manager}")
                    setattr(tech, "is_manager", p.is_manager)
                if updates:
                    actions.append(f"UPDATE Technician({u.username}): " + "; ".join(updates))
                    tech.save()
            else:
                actions.append(f"ENSURE Technician(user for {p.email}) role='{p.role}' is_manager={p.is_manager}")

        # --- Optionally deactivate users not in the TEAM list ---
        if deactivate_missing:
            qs = User.objects.filter(
                email__iregex=r"@(?:lgisolutions\.com|logibe\.com)$"
            )
            for user in qs:
                if user.email.lower() not in new_emails and user.email.lower() not in legacy_emails:
                    if user.is_active:
                        actions.append(f"DEACTIVATE {user.username} ({user.email})")
                        if commit:
                            user.is_active = False
                            user.save()

        # --- Report ---
        if not actions:
            self.stdout.write(self.style.SUCCESS("Nothing to do."))
            return

        mode = "APPLY" if commit else "DRY-RUN"
        self.stdout.write(self.style.WARNING(f"== {mode} =="))
        for a in actions:
            self.stdout.write(" - " + a)
        if warnings:
            self.stdout.write(self.style.NOTICE("\nWarnings:"))
            for w in warnings:
                self.stdout.write(" * " + w)

        if not commit:
            self.stdout.write(
                self.style.WARNING(
                    "\nNo changes were made (dry-run). Re-run with --commit to apply."
                )
            )
