"""Registers the project's recurring jobs.

Run once after deploying:  python manage.py setup_schedules

Safe to run repeatedly - it updates the existing row instead of creating
duplicates.
"""

from django.core.management.base import BaseCommand
from django_q.models import Schedule


class Command(BaseCommand):
    help = "Create or update the scheduled background jobs."

    def handle(self, *args, **options):
        schedule, created = Schedule.objects.update_or_create(
            name="sla-breach-sweep",
            defaults={
                "func": "notifications.tasks.check_sla_breaches",
                "schedule_type": Schedule.HOURLY,
                # repeats=-1 means "forever". A positive number would run
                # that many times and then stop.
                "repeats": -1,
            },
        )

        verb = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(f"{verb} schedule '{schedule.name}' ({schedule.func})")
        )
