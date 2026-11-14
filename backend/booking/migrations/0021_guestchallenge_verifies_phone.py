from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('booking', '0020_place_allocation_exclusion_and_drop_room_exclusion')]
    operations = [migrations.AddField(model_name='guestchallenge', name='verifies_phone', field=models.BooleanField(default=False)),
                  migrations.RunSQL('ALTER TABLE booking_guestchallenge ALTER COLUMN verifies_phone SET DEFAULT false',
                                    'ALTER TABLE booking_guestchallenge ALTER COLUMN verifies_phone DROP DEFAULT')]
