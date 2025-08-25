import random
from faker import Faker
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from crm_app.models import Project, Technician

User = get_user_model()
fake = Faker('fr_CA')

class Command(BaseCommand):
    help = 'Seeds the database with 105 projects with random statuses and new products.'

    def handle(self, *args, **options):
        self.stdout.write('Seeding 105 projects...')

        products = [
            "GRH", "Sicheld", "Med Echo", "I-CLSC", "RadImage",
            "eClinibase", "Ofys", "Dossier Sante", "Gestion Acces", "Ressources Humaines"
        ]
        
        statuses = [
            "pending", "in_progress", "completed", "on_hold", "cancelled",
            "assigned", "waiting_on_client", "waiting_on_internal",
            "preparation", "production"
        ]

        technicians = list(Technician.objects.all())
        if not technicians:
            self.stdout.write(self.style.ERROR('No technicians found. Please create some technicians first.'))
            return

        for i in range(105):
            tech = random.choice(technicians)
            project_status = random.choice(statuses)
            product_name = random.choice(products)
            
            project_number = f"PRJ{3000 + i}"
            
            Project.objects.create(
                project_number=project_number,
                title=f"{product_name} - {fake.company()}",
                client_name=fake.company(),
                product=product_name,
                environment=random.choice(['test', 'prod']),
                work_type=random.choice([wt[0] for wt in Project.WORK_TYPE_CHOICES]),
                status=project_status,
                technician=tech,
                assigned_to=tech.user,
                created_by=tech.user,
                date=fake.date_between(start_date='-2y', end_date='today'),
                start_at=fake.date_time_between(start_date='-1y', end_date='now'),
                end_at=fake.date_time_between(start_date='now', end_date='+1y'),
            )

        self.stdout.write(self.style.SUCCESS('Successfully seeded 105 projects.'))
