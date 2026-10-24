from django.core.management.base import BaseCommand

from apps.reservations.services import expire_holds


class Command(BaseCommand):
    help = "Expire timed-out holds and advance reservation queues."

    def handle(self, *args, **options):
        expired_ids = expire_holds()
        self.stdout.write(f"Expired {len(expired_ids)} reservation hold(s).")
