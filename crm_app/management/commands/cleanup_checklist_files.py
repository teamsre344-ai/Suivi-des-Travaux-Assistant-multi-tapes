from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from crm_app.models import Project, ChecklistItemImage


class Command(BaseCommand):
    help = "Supprime les images de checklist plus d'une semaine après la fin du projet"

    def handle(self, *args, **kwargs):
        cutoff = timezone.now() - timedelta(days=7)
        # Use validation_completed_at if present, else updated_at

        # Simpler: iterate only completed projects
        deleted, kept = 0, 0
        for p in Project.objects.filter(status="completed"):
            done_at = p.validation_completed_at or p.updated_at
            if not done_at or done_at > cutoff:
                continue
            # Delete all images for this project
            for img in ChecklistItemImage.objects.filter(item__project=p):
                try:
                    f = img.image
                    img.delete()
                    if f:
                        f.storage.delete(f.name)
                    deleted += 1
                except Exception:
                    kept += 1

        self.stdout.write(
            self.style.SUCCESS(f"Images supprimées: {deleted} (gardées: {kept})")
        )
