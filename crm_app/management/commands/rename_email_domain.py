from django.core.management.base import BaseCommand
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = "Rewrite all user emails from old corporate domains to @lgisolutions.com (by local part)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--commit", action="store_true", help="Apply changes (otherwise dry-run)"
        )
        parser.add_argument(
            "--from-domains",
            nargs="+",
            default=["logibec.com", "logibe.com"],
            help="Old domains",
        )
        parser.add_argument(
            "--to-domain", default="lgisolutions.com", help="Target domain"
        )

    def handle(self, *args, **opts):
        commit = opts["commit"]
        old_domains = set(d.lower() for d in opts["from_domains"])
        new_domain = opts["to_domain"].lower()

        changed, skipped_dupe = 0, 0
        for u in User.objects.exclude(email="").all():
            e = u.email.strip().lower()
            if "@" not in e:
                continue
            local, domain = e.split("@", 1)
            if domain not in old_domains:
                continue
            new_email = f"{local}@{new_domain}"

            # skip if another account already owns the new email
            if User.objects.filter(email__iexact=new_email).exclude(pk=u.pk).exists():
                self.stdout.write(
                    self.style.WARNING(f"SKIP (email exists): {u.email} -> {new_email}")
                )
                skipped_dupe += 1
                continue

            if commit:
                u.email = new_email
                # optionally normalize username to local part
                if u.username != local:
                    u.username = local
                u.save(update_fields=["email", "username"])
            self.stdout.write(
                f"{'UPDATED' if commit else 'WOULD UPDATE'}: {e} -> {new_email}"
            )
            changed += 1

        suffix = "" if commit else " (dry-run)"
        self.stdout.write(
            self.style.SUCCESS(
                f"Done{suffix}. Changed={changed}, skipped_duplicates={skipped_dupe}"
            )
        )
