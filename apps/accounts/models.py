from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    email = models.EmailField(unique=True)

    class Meta:
        permissions = (
            ("manage_users", "Can create and manage library accounts"),
            ("assign_roles", "Can assign library roles"),
        )
