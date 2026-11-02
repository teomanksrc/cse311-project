from django.apps import AppConfig


class ScoringConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "scoring"

    def ready(self):
        from scoring import signals  # noqa: F401
