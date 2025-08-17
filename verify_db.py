import django
django.setup()
from django.conf import settings
from django.db import connection

print("ENGINE:", settings.DATABASES["default"]["ENGINE"])
print("NAME:", settings.DATABASES["default"]["NAME"])
print("VENDOR:", connection.vendor)

with connection.cursor() as c:
    c.execute("SELECT current_database(), version()")
    print("DB, Version:", c.fetchone())
