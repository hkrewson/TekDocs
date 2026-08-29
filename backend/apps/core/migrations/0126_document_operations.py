from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0125_document_placement_audiences"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="collection",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="document",
            name="tags",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="document",
            name="owner",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="owned_documents",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="document",
            name="review_due_on",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="document",
            name="review_state",
            field=models.CharField(
                choices=[
                    ("unreviewed", "Unreviewed"),
                    ("pending", "Pending review"),
                    ("approved", "Approved"),
                    ("changes_requested", "Changes requested"),
                ],
                default="unreviewed",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="document",
            name="review_requested_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="requested_document_reviews",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="document",
            name="review_requested_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="document",
            name="reviewer",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="assigned_document_reviews",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="document",
            name="review_decided_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="document",
            name="last_reviewed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="reviewed_documents",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="document",
            name="last_reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="document",
            name="review_note",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddConstraint(
            model_name="document",
            constraint=models.CheckConstraint(
                condition=models.Q(("review_state__in", ["unreviewed", "pending", "approved", "changes_requested"])),
                name="document_review_state_supported",
            ),
        ),
        migrations.AddConstraint(
            model_name="document",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        ("review_decided_at__isnull", True),
                        ("review_requested_at__isnull", False),
                        ("review_requested_by__isnull", False),
                        ("review_state", "pending"),
                        ("reviewer__isnull", False),
                    )
                    | ~models.Q(("review_state", "pending"))
                ),
                name="document_pending_review_shape",
            ),
        ),
        migrations.AddIndex(
            model_name="document",
            index=models.Index(
                fields=["tenant", "organization", "review_state", "review_due_on"],
                name="core_doc_review_health_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="document",
            index=models.Index(
                fields=["tenant", "organization", "collection", "archived_at"],
                name="core_doc_collection_idx",
            ),
        ),
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE FUNCTION tekdocs_validate_document_people_scope() RETURNS trigger
            LANGUAGE plpgsql AS $$
            DECLARE
              person_id uuid;
            BEGIN
              FOREACH person_id IN ARRAY ARRAY[
                NEW.owner_id,
                NEW.review_requested_by_id,
                NEW.reviewer_id,
                NEW.last_reviewed_by_id
              ] LOOP
                IF person_id IS NOT NULL AND NOT EXISTS (
                  SELECT 1
                  FROM accounts_tenantmembership membership
                  WHERE membership.tenant_id = NEW.tenant_id
                    AND (
                      membership.organization_id IS NULL
                      OR membership.organization_id IS NOT DISTINCT FROM NEW.organization_id
                    )
                    AND membership.user_id = person_id
                ) THEN
                  RAISE EXCEPTION 'document owner and review participants must belong to its authorized workspace';
                END IF;
              END LOOP;
              RETURN NEW;
            END $$;

            CREATE TRIGGER core_document_people_scope_guard
            BEFORE INSERT OR UPDATE OF tenant_id, organization_id, owner_id,
              review_requested_by_id, reviewer_id, last_reviewed_by_id
            ON core_document
            FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_document_people_scope();
            """,
            reverse_sql="""
            DROP TRIGGER IF EXISTS core_document_people_scope_guard ON core_document;
            DROP FUNCTION IF EXISTS tekdocs_validate_document_people_scope();
            """,
        ),
        migrations.AlterField(
            model_name="reminderschedule",
            name="domain",
            field=models.CharField(
                choices=[
                    ("compliance", "Compliance"),
                    ("inventory", "Inventory"),
                    ("domain", "Domain"),
                    ("documentation", "Documentation"),
                ],
                max_length=20,
            ),
        ),
    ]
