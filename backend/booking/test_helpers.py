"""Explicit unrelated owner for secondary-property authorization fixtures."""

from .models import User


def unrelated_owner():
    user, _ = User.objects.get_or_create(
        email="unrelated-owner@example.test",
        defaults={
            "username": "unrelated-owner@example.test",
            "name": "Unrelated test owner",
            "password": "!",
        },
    )
    return user
