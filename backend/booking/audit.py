"""Redacted audit records written inside the owning workflow transaction."""

from .models import Audit


def log_change(user, entity, item, action, before, after, resort_id=None, website=False):
    def redact(data):
        if data is None:
            return None
        return {k: v for k, v in data.items() if k not in ["guestPhone", "password", "staffNotes"]}

    Audit.objects.create(
        actor="Гость сайта" if website else (user.name or user.username),
        resort_id=resort_id,
        entity=entity,
        entity_id=str(item.pk),
        action=action,
        label=(after or before or {}).get("name", (after or before or {}).get("roomName", entity)),
        before=redact(before),
        after=redact(after),
    )
