import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

FORWARD_SQL = """
CREATE FUNCTION tekdocs_validate_repository_evidence_review() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_repositorypublicationevidence evidence
    WHERE evidence.id=NEW.evidence_id AND evidence.tenant_id=NEW.tenant_id
      AND evidence.organization_id IS NOT DISTINCT FROM NEW.organization_id
      AND evidence.workspace_id=NEW.workspace_id AND evidence.audience='client_visible'
  ) THEN RAISE EXCEPTION 'repository evidence review scope mismatch' USING ERRCODE='23514'; END IF;
  IF NEW.outcome='accepted_for_packaging' AND EXISTS (
    SELECT 1 FROM core_repositorypublicationevidence evidence
    WHERE evidence.id=NEW.evidence_id AND evidence.signed_by_id=NEW.actor_id
  ) THEN RAISE EXCEPTION 'repository evidence signer cannot accept own evidence' USING ERRCODE='23514'; END IF;
  RETURN NEW;
END $$;
CREATE FUNCTION tekdocs_guard_repository_evidence_review() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'repository evidence review is append-only' USING ERRCODE='23514';
END $$;
CREATE TRIGGER core_repositoryevidencereviewdecision_validate
BEFORE INSERT ON core_repositoryevidencereviewdecision
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_repository_evidence_review();
CREATE TRIGGER core_repositoryevidencereviewdecision_immutable
BEFORE UPDATE OR DELETE ON core_repositoryevidencereviewdecision
FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_repository_evidence_review();
ALTER TABLE core_repositoryevidencereviewdecision ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_repositoryevidencereviewdecision FORCE ROW LEVEL SECURITY;
CREATE POLICY core_repositoryevidencereviewdecision_runtime_scope ON core_repositoryevidencereviewdecision
USING (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id))
WITH CHECK (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id));
"""

REVERSE_SQL = """
DROP POLICY IF EXISTS core_repositoryevidencereviewdecision_runtime_scope ON core_repositoryevidencereviewdecision;
ALTER TABLE core_repositoryevidencereviewdecision NO FORCE ROW LEVEL SECURITY;
ALTER TABLE core_repositoryevidencereviewdecision DISABLE ROW LEVEL SECURITY;
DROP TRIGGER IF EXISTS core_repositoryevidencereviewdecision_immutable ON core_repositoryevidencereviewdecision;
DROP TRIGGER IF EXISTS core_repositoryevidencereviewdecision_validate ON core_repositoryevidencereviewdecision;
DROP FUNCTION IF EXISTS tekdocs_guard_repository_evidence_review();
DROP FUNCTION IF EXISTS tekdocs_validate_repository_evidence_review();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0170_repository_evidence_pdf"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RepositoryEvidenceReviewDecision",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "outcome",
                    models.CharField(
                        choices=[("accepted_for_packaging", "Accepted for packaging"), ("rejected", "Rejected")],
                        max_length=24,
                    ),
                ),
                ("reason", models.CharField(max_length=500)),
                ("occurred_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("actor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                (
                    "evidence",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="review_decision",
                        to="core.repositorypublicationevidence",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="core.organization"
                    ),
                ),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.tenant")),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.workspace")),
            ],
            options={
                "ordering": ("-occurred_at", "id"),
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(outcome__in=["accepted_for_packaging", "rejected"]),
                        name="repository_review_outcome_valid",
                    ),
                    models.CheckConstraint(condition=~models.Q(reason=""), name="repository_review_reason_required"),
                ],
            },
        ),
        migrations.RunSQL(FORWARD_SQL, REVERSE_SQL),
    ]
