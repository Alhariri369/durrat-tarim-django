from django.conf import settings
from django.db import models
from django.utils import timezone


class Ticket(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "جديد"
        IN_PROGRESS = "in_progress", "قيد المعالجة"
        COMPLETED = "completed", "مكتمل"
        REJECTED_SPAM = "rejected_spam", "مرفوض / مزعج"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tickets",
    )
    user_name_snapshot = models.CharField(max_length=250, blank=True)
    user_email_snapshot = models.CharField(max_length=320, blank=True)
    name = models.CharField(max_length=200, db_index=True)
    phone = models.CharField(max_length=100)
    subject = models.TextField()
    details = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
        db_index=True,
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tickets",
    )
    creation_date = models.DateTimeField(default=timezone.now)
    date_edited = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "tickets"
        ordering = ["-creation_date"]

    def save(self, *args, **kwargs):
        self.date_edited = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name}: {self.subject}"
