from django.core.management.base import BaseCommand
import time
from django.db import connections
from django.db.utils import OperationalError

class Command(BaseCommand):
    help = "Waits for the database to be available"

    def handle(self, *args, **options):
        self.stdout.write("Waiting for database...")
        db_conn = None
        while not db_conn:
            try:
                db_conn = connections['default']
                db_conn.cursor()  # Try to create a cursor to verify connection
            except OperationalError:
                self.stdout.write(self.style.WARNING("Database unavailable, waiting 1 second..."))
                time.sleep(1)
        self.stdout.write(self.style.SUCCESS("Database available!"))
