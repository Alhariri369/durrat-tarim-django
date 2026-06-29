from django.db import models
from django.utils import timezone


class Ticket(models.Model):
    name = models.CharField(max_length=200, db_index=True)
    phone = models.CharField(max_length=100)
    subject = models.TextField()
    details = models.TextField()
    is_completed = models.BooleanField(default=False)
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
