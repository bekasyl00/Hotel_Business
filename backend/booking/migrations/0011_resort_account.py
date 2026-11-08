from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def assign_accounts(apps, schema_editor):
    Resort = apps.get_model('booking', 'Resort')
    User = apps.get_model('booking', 'User')
    alias = schema_editor.connection.alias
    users = User.objects.using(alias)
    fallback = users.filter(role='admin', is_active=True).order_by('id').first()
    fallback = fallback or users.filter(is_superuser=True, is_active=True).order_by('id').first()
    for resort in Resort.objects.using(alias).all().iterator():
        owner = users.filter(resort_id=resort.pk, role='manager').order_by('-is_active', 'id').first()
        owner = owner or fallback
        if owner is None:
            raise RuntimeError('Create an active platform administrator before assigning existing resorts.')
        resort.account_id = owner.pk
        resort.save(using=alias, update_fields=['account'])


class Migration(migrations.Migration):
    dependencies = [('booking', '0010_alter_user_role')]
    operations = [
        migrations.AddField(
            model_name='resort', name='account',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='managed_resorts'),
        ),
        migrations.RunPython(assign_accounts, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='resort', name='account',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.PROTECT, related_name='managed_resorts'),
        ),
    ]
