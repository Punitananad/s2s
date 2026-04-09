from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hotelportal", "0014_request_is_paid"),
    ]

    operations = [
        migrations.AddField(
            model_name="stay",
            name="id_type",
            field=models.CharField(
                blank=True, default="", max_length=10,
                choices=[("AADHAAR","Aadhaar"),("PASSPORT","Passport"),("DL","Driving License"),("OTHER","Other")],
            ),
        ),
        migrations.AddField(
            model_name="stay",
            name="id_number",
            field=models.CharField(blank=True, default="", max_length=50),
        ),
        migrations.AddField(
            model_name="stay",
            name="aadhaar_number",
            field=models.CharField(blank=True, default="", max_length=12),
        ),
        migrations.AddField(
            model_name="stay",
            name="age",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="stay",
            name="gender",
            field=models.CharField(
                blank=True, default="", max_length=1,
                choices=[("M","Male"),("F","Female"),("O","Other")],
            ),
        ),
        migrations.AddField(
            model_name="stay",
            name="city",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="stay",
            name="state",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="stay",
            name="address",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="stay",
            name="id_proof",
            field=models.FileField(blank=True, null=True, upload_to="id_proofs/"),
        ),
        migrations.AddField(
            model_name="stay",
            name="signature_data",
            field=models.TextField(blank=True, default=""),
        ),
    ]
