from django.db import migrations, models
import booking.models


def populate(apps, schema_editor):
    Booking = apps.get_model('booking', 'Booking')
    bookings = Booking.objects.using(schema_editor.connection.alias)
    for booking in bookings.filter(public_code__isnull=True).iterator(chunk_size=1000):
        # Generate separately for every historical row, never reuse a migration default.
        code = new_code()
        while bookings.filter(public_code=code).exists():
            code = new_code()
        bookings.filter(pk=booking.pk).update(public_code=code)


def new_code():
    return booking.models.new_booking_code()


class Migration(migrations.Migration):
    dependencies = [('booking', '0021_guestchallenge_verifies_phone')]
    operations = [
        migrations.AddField(model_name='booking', name='public_code',
                            field=models.CharField(max_length=10, null=True, unique=True, editable=False)),
        migrations.RunPython(populate, migrations.RunPython.noop),
        migrations.AlterField(model_name='booking', name='public_code',
                              field=models.CharField(max_length=10, unique=True, editable=False,
                                                     default=booking.models.new_booking_code)),
        # Old API instances omit this column during rollout/rollback. Keep an SQL
        # fallback so they can still insert; newer instances use the Python generator.
        migrations.RunSQL(
            "ALTER TABLE booking_booking ALTER COLUMN public_code SET DEFAULT "
            "translate(upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 10)), '01', 'GH')",
            "ALTER TABLE booking_booking ALTER COLUMN public_code DROP DEFAULT",
        ),
    ]
