from django.apps import AppConfig

class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'

    def ready(self):
        try:
            from django_q.models import Schedule
            from django.db.utils import ProgrammingError, OperationalError
            # Create a schedule if it doesn't exist, safely ignoring when running migrations
            try:
                Schedule.objects.get_or_create(
                    func='api.tasks.cleanup_stuck_payouts',
                    defaults={
                        'schedule_type': Schedule.MINUTES,
                        'minutes': 1,
                        'repeats': -1
                    }
                )
            except (ProgrammingError, OperationalError):
                pass
        except ImportError:
            pass
