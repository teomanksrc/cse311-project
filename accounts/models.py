from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        HEAD = "HEAD", "Department Head"
        INSTRUCTOR = "INSTRUCTOR", "Instructor"
        STUDENT = "STUDENT", "Student"

    role = models.CharField(max_length=12, choices=Role.choices, default=Role.STUDENT)
    student_number = models.CharField(max_length=20, unique=True, null=True, blank=True)

    @property
    def is_admin_or_head(self):
        return self.role in (self.Role.ADMIN, self.Role.HEAD)

    @property
    def is_instructor(self):
        return self.role == self.Role.INSTRUCTOR

    @property
    def is_student(self):
        return self.role == self.Role.STUDENT

    def __str__(self):
        return self.get_full_name() or self.username
