import re
import uuid
from pathlib import PurePosixPath

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models.functions import Lower
from django.utils import timezone

from .document_keys import BINDING_NAME_PATTERN
from .scoping import OrganizationScopedManager, TenantScopedManager

WORKSPACE_UUID_NAMESPACE = uuid.UUID("6890dc87-8d91-4f76-a6eb-99dfd06904a5")


def workspace_identity_uuid(*, tenant_id: uuid.UUID, organization_id: uuid.UUID | None) -> uuid.UUID:
    owner = "msp" if organization_id is None else f"organization:{organization_id}"
    return uuid.uuid5(WORKSPACE_UUID_NAMESPACE, f"tenant:{tenant_id}:{owner}")


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Tenant(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        creating = self._state.adding
        with transaction.atomic():
            super().save(*args, **kwargs)
            if creating:
                Workspace.objects.get_or_create(
                    id=workspace_identity_uuid(tenant_id=self.id, organization_id=None),
                    tenant=self,
                    kind=WorkspaceKind.MSP,
                    organization=None,
                )


class TenantBillingProfile(TimestampedModel):
    """Tenant issuer identity and invoice defaults; no receivable state."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.OneToOneField(Tenant, on_delete=models.PROTECT, related_name="billing_profile")
    legal_name = models.CharField(max_length=240, blank=True)
    address_line_1 = models.CharField(max_length=240, blank=True)
    address_line_2 = models.CharField(max_length=240, blank=True)
    city = models.CharField(max_length=120, blank=True)
    region = models.CharField(max_length=120, blank=True)
    postal_code = models.CharField(max_length=32, blank=True)
    country_code = models.CharField(max_length=2, blank=True)
    billing_email = models.EmailField(max_length=254, blank=True)
    phone = models.CharField(max_length=64, blank=True)
    tax_registration = models.CharField(max_length=120, blank=True)
    default_currency = models.CharField(max_length=3, default="USD")
    payment_terms_days = models.PositiveSmallIntegerField(default=30)
    invoice_prefix = models.CharField(max_length=16, default="INV")
    invoice_date_component = models.CharField(
        max_length=24,
        choices=(
            ("none", "No date"),
            ("year", "Four-digit year"),
            ("short_year", "Two-digit year"),
            ("year_month", "Year and month"),
            ("short_year_month", "Short year and month"),
            ("month_year", "Month and year"),
            ("month_short_year", "Month and short year"),
            ("year_month_code", "Year and month letter"),
            ("short_year_month_code", "Short year and month letter"),
        ),
        default="none",
    )
    invoice_separator = models.CharField(
        max_length=1,
        choices=(("-", "Hyphen"), ("/", "Slash"), (".", "Period"), ("", "None")),
        default="-",
        blank=True,
    )
    invoice_sequence_digits = models.PositiveSmallIntegerField(default=6)
    invoice_reset_period = models.CharField(
        max_length=8,
        choices=(("never", "Never"), ("yearly", "Every year"), ("monthly", "Every month")),
        default="never",
    )

    objects = models.Manager()
    scoped = TenantScopedManager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(payment_terms_days__lte=365),
                name="billing_profile_payment_terms_bounded",
            ),
        ]

    def __str__(self) -> str:
        return self.legal_name or self.tenant.name

    def clean(self) -> None:
        from .countries import COUNTRY_CODES
        from .money import MoneyError, normalize_currency

        try:
            self.default_currency = normalize_currency(self.default_currency)
        except MoneyError as exc:
            raise ValidationError({"default_currency": str(exc)}) from exc
        self.country_code = self.country_code.strip().upper()
        self.invoice_prefix = self.invoice_prefix.strip().upper()
        if self.country_code and self.country_code not in COUNTRY_CODES:
            raise ValidationError({"country_code": "Choose a supported ISO country"})
        if not re.fullmatch(r"[A-Z0-9-]{1,16}", self.invoice_prefix):
            raise ValidationError({"invoice_prefix": "Prefix may contain uppercase letters, numbers, and hyphens"})
        if not 1 <= self.invoice_sequence_digits <= 12:
            raise ValidationError({"invoice_sequence_digits": "Sequence digits must be between 1 and 12"})
        if self.invoice_reset_period == "yearly" and self.invoice_date_component == "none":
            raise ValidationError({"invoice_date_component": "Include a year when numbering restarts each year"})
        if self.invoice_reset_period == "monthly" and self.invoice_date_component not in {
            "year_month",
            "short_year_month",
            "month_year",
            "month_short_year",
            "year_month_code",
            "short_year_month_code",
        }:
            raise ValidationError(
                {"invoice_date_component": "Include a year and month when numbering restarts each month"}
            )

    @property
    def is_issue_ready(self) -> bool:
        required = (
            self.legal_name,
            self.address_line_1,
            self.city,
            self.postal_code,
            self.country_code,
            self.billing_email,
        )
        return all(value.strip() for value in required)


class TaxRate(models.Model):
    """One immutable version of an operator-selected tenant tax rate."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="tax_rates")
    series_id = models.UUIDField(default=uuid.uuid4, editable=False)
    version = models.PositiveIntegerField(default=1)
    name = models.CharField(max_length=120)
    rate = models.DecimalField(max_digits=9, decimal_places=6)
    inclusive = models.BooleanField(default=False)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = TenantScopedManager()

    class Meta:
        ordering = ("name", "-version", "id")
        constraints = [
            models.UniqueConstraint(fields=("tenant", "series_id", "version"), name="tax_rate_version_unique"),
            models.CheckConstraint(condition=models.Q(version__gte=1), name="tax_rate_version_positive"),
            models.CheckConstraint(condition=models.Q(rate__gte=0), name="tax_rate_nonnegative"),
            models.CheckConstraint(
                condition=models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=models.F("effective_from")),
                name="tax_rate_effective_range_valid",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant", "series_id", "version"), name="core_taxrate_series_idx"),
            models.Index(fields=("tenant", "effective_from", "effective_to"), name="core_taxrate_effective_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.name} v{self.version}"

    def save(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        if self._state.adding is False:
            raise ValidationError("Tax rate versions are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Tax rate versions are immutable")

    def clean(self) -> None:
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "Effective end cannot precede effective start"})


class ServiceRate(TimestampedModel):
    """A reusable tenant-owned sell rate; invoice lines retain a snapshot."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="service_rates")
    name = models.CharField(max_length=160)
    description = models.CharField(max_length=1000, blank=True)
    unit_amount = models.DecimalField(max_digits=18, decimal_places=4)
    currency = models.CharField(max_length=3)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = TenantScopedManager()

    class Meta:
        ordering = ("name", "id")
        constraints = [
            models.CheckConstraint(condition=models.Q(unit_amount__gte=0), name="service_rate_amount_nonnegative"),
            models.UniqueConstraint(
                Lower("name"),
                "tenant",
                condition=models.Q(archived_at__isnull=True),
                name="service_rate_name_active_unique",
            ),
        ]
        indexes = [models.Index(fields=("tenant", "archived_at", "name"), name="core_servicerate_scope_idx")]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        from .money import MoneyError, normalize_currency, validate_amount

        try:
            self.currency = normalize_currency(self.currency)
            validate_amount(self.unit_amount, self.currency)
        except MoneyError as exc:
            raise ValidationError({"unit_amount": str(exc)}) from exc


class InvoiceState(models.TextChoices):
    DRAFT = "draft", "Draft"
    ISSUED = "issued", "Issued"


class InvoiceNumberSeries(TimestampedModel):
    """A tenant-owned transactional counter used only while issuing invoices."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="invoice_number_series")
    prefix = models.CharField(max_length=16)
    date_component = models.CharField(max_length=24, default="none")
    separator = models.CharField(max_length=1, default="-", blank=True)
    sequence_digits = models.PositiveSmallIntegerField(default=6)
    reset_period = models.CharField(max_length=8, default="never")
    current_period = models.CharField(max_length=7, blank=True, default="")
    next_number = models.PositiveBigIntegerField(default=1)

    objects = models.Manager()
    scoped = TenantScopedManager()

    class Meta:
        ordering = ("prefix", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("tenant", "prefix", "date_component", "separator", "sequence_digits", "reset_period"),
                name="invoice_series_format_unique",
            ),
            models.CheckConstraint(condition=models.Q(next_number__gte=1), name="invoice_series_next_positive"),
            models.CheckConstraint(
                condition=models.Q(sequence_digits__gte=1, sequence_digits__lte=12),
                name="invoice_series_digits_bounded",
            ),
        ]

    def __str__(self) -> str:
        return self.prefix

    def clean(self) -> None:
        self.prefix = self.prefix.strip().upper()
        if not re.fullmatch(r"[A-Z0-9-]{1,16}", self.prefix):
            raise ValidationError({"prefix": "Prefix may contain uppercase letters, numbers, and hyphens"})
        if self.date_component not in {
            "none",
            "year",
            "short_year",
            "year_month",
            "short_year_month",
            "month_year",
            "month_short_year",
            "year_month_code",
            "short_year_month_code",
        }:
            raise ValidationError({"date_component": "Unsupported invoice date component"})
        if self.separator not in {"-", "/", ".", ""}:
            raise ValidationError({"separator": "Unsupported invoice number separator"})
        if self.reset_period not in {"never", "yearly", "monthly"}:
            raise ValidationError({"reset_period": "Unsupported invoice reset period"})
        if not 1 <= self.sequence_digits <= 12:
            raise ValidationError({"sequence_digits": "Sequence digits must be between 1 and 12"})
        if self.reset_period == "yearly" and self.date_component == "none":
            raise ValidationError({"date_component": "Include a year when numbering restarts each year"})
        if self.reset_period == "monthly" and self.date_component not in {
            "year_month",
            "short_year_month",
            "month_year",
            "month_short_year",
            "year_month_code",
            "short_year_month_code",
        }:
            raise ValidationError({"date_component": "Include a year and month when numbering restarts each month"})


class Invoice(TimestampedModel):
    """An exact-Workspace invoice that becomes immutable when issued."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="invoices")
    organization = models.ForeignKey("Organization", on_delete=models.PROTECT, related_name="invoices")
    entity = models.OneToOneField("Entity", on_delete=models.PROTECT, related_name="invoice")
    state = models.CharField(max_length=16, choices=InvoiceState.choices, default=InvoiceState.DRAFT)
    number_series = models.ForeignKey(
        InvoiceNumberSeries,
        on_delete=models.PROTECT,
        related_name="invoices",
        null=True,
        blank=True,
    )
    number = models.CharField(max_length=64, blank=True)
    series_year = models.PositiveSmallIntegerField(null=True, blank=True)
    series_sequence = models.PositiveBigIntegerField(null=True, blank=True)
    currency = models.CharField(max_length=3)
    invoice_date = models.DateField()
    due_date = models.DateField()
    reference = models.CharField(max_length=240, blank=True)
    notes = models.TextField(blank=True)
    issuer_snapshot = models.JSONField(default=dict, blank=True)
    customer_snapshot = models.JSONField(default=dict, blank=True)
    key_resolutions = models.JSONField(default=list, blank=True)
    subtotal_amount = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    tax_amount = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    total_amount = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    content_digest = models.CharField(max_length=64, blank=True)
    signature = models.TextField(blank=True)
    signature_algorithm = models.CharField(max_length=20, blank=True)
    public_key = models.TextField(blank=True)
    key_fingerprint = models.CharField(max_length=64, blank=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="issued_invoices",
        null=True,
        blank=True,
    )
    issued_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    delivered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="delivered_invoices",
        null=True,
        blank=True,
    )
    delivery_recipient = models.EmailField(blank=True)
    delivery_count = models.PositiveIntegerField(default=0)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-invoice_date", "-created_at", "id")
        constraints = [
            models.CheckConstraint(condition=models.Q(state__in=InvoiceState.values), name="invoice_state_valid"),
            models.CheckConstraint(
                condition=models.Q(due_date__gte=models.F("invoice_date")), name="invoice_due_date_valid"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        state=InvoiceState.DRAFT,
                        number_series__isnull=True,
                        number="",
                        series_year__isnull=True,
                        series_sequence__isnull=True,
                        subtotal_amount__isnull=True,
                        tax_amount__isnull=True,
                        total_amount__isnull=True,
                        issued_by__isnull=True,
                        issued_at__isnull=True,
                        content_digest="",
                        signature="",
                        signature_algorithm="",
                        public_key="",
                        key_fingerprint="",
                    )
                    | models.Q(
                        state=InvoiceState.ISSUED,
                        number_series__isnull=False,
                        number__gt="",
                        series_sequence__isnull=False,
                        subtotal_amount__isnull=False,
                        tax_amount__isnull=False,
                        total_amount__isnull=False,
                        issued_by__isnull=False,
                        issued_at__isnull=False,
                        content_digest__regex=r"^[0-9a-f]{64}$",
                        signature__gt="",
                        signature_algorithm="Ed25519",
                        public_key__gt="",
                        key_fingerprint__regex=r"^[0-9a-f]{64}$",
                    )
                ),
                name="invoice_issue_fields_consistent",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(state=InvoiceState.DRAFT)
                    | models.Q(total_amount=models.F("subtotal_amount") + models.F("tax_amount"))
                ),
                name="invoice_stored_totals_reconcile",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        delivery_count=0,
                        delivered_at__isnull=True,
                        delivered_by__isnull=True,
                        delivery_recipient="",
                    )
                    | models.Q(
                        state=InvoiceState.ISSUED,
                        delivery_count__gte=1,
                        delivered_at__isnull=False,
                        delivered_by__isnull=False,
                        delivery_recipient__gt="",
                    )
                ),
                name="invoice_delivery_fields_consistent",
            ),
            models.UniqueConstraint(
                fields=("tenant", "number"),
                condition=~models.Q(number=""),
                name="invoice_number_unique",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "state", "invoice_date"), name="core_invoice_scope_idx")
        ]

    def __str__(self) -> str:
        return self.entity.display_name

    def clean(self) -> None:
        from .money import MoneyError, normalize_currency

        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id
            or self.entity.organization_id != self.organization_id
            or self.entity.entity_type != "invoice"
            or self.entity.visibility != "msp_private"
        ):
            raise ValidationError("Invoice entity identity, scope, and visibility must match")
        if self.organization_id and self.organization.tenant_id != self.tenant_id:
            raise ValidationError("Invoice organization must belong to its tenant")
        if self.due_date and self.invoice_date and self.due_date < self.invoice_date:
            raise ValidationError({"due_date": "Due date cannot precede invoice date"})
        try:
            self.currency = normalize_currency(self.currency)
        except MoneyError as exc:
            raise ValidationError({"currency": str(exc)}) from exc
        number_series = self.number_series
        if self.number_series_id and (number_series is None or number_series.tenant_id != self.tenant_id):
            raise ValidationError("Invoice number series must belong to its tenant")


def invoice_artifact_upload_to(instance: "InvoiceArtifact", _filename: str) -> str:
    """Return an opaque retained-artifact key without customer-authored path material."""

    return str(
        PurePosixPath("invoice-artifacts") / str(instance.tenant_id) / str(instance.invoice_id) / str(instance.id)
    )


class InvoiceArtifact(models.Model):
    """The append-only retained PDF produced by one invoice issue transition."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="invoice_artifacts")
    organization = models.ForeignKey("Organization", on_delete=models.PROTECT, related_name="invoice_artifacts")
    invoice = models.OneToOneField(Invoice, on_delete=models.PROTECT, related_name="artifact")
    file = models.FileField(upload_to=invoice_artifact_upload_to, max_length=500)
    original_filename = models.CharField(max_length=240)
    media_type = models.CharField(max_length=120, default="application/pdf")
    size = models.PositiveBigIntegerField()
    checksum = models.CharField(max_length=64)
    created_at = models.DateTimeField()

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        indexes = [models.Index(fields=("tenant", "organization", "invoice"), name="core_invart_scope_idx")]

    def __str__(self) -> str:
        return self.original_filename

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ValidationError("Issued invoice artifacts are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Issued invoice artifacts are retained")

    def clean(self) -> None:
        if self.invoice_id and (
            self.invoice.tenant_id != self.tenant_id
            or self.invoice.organization_id != self.organization_id
            or self.invoice.state != InvoiceState.ISSUED
        ):
            raise ValidationError("Invoice artifact must belong to an issued invoice in the same Workspace")
        if self.media_type != "application/pdf":
            raise ValidationError("Invoice artifacts must be PDFs")
        if not re.fullmatch(r"[0-9a-f]{64}", self.checksum):
            raise ValidationError("Invoice artifact checksum is invalid")


class InvoiceLine(TimestampedModel):
    """A draft line whose sell values never resolve through its optional origin."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="invoice_lines")
    organization = models.ForeignKey("Organization", on_delete=models.PROTECT, related_name="invoice_lines")
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveSmallIntegerField(default=1)
    description = models.CharField(max_length=1000)
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=1)
    unit_amount = models.DecimalField(max_digits=18, decimal_places=4)
    currency = models.CharField(max_length=3)
    tax_rate_name = models.CharField(max_length=120, blank=True)
    tax_rate_value = models.DecimalField(max_digits=9, decimal_places=6, default=0)
    tax_inclusive = models.BooleanField(default=False)
    catalog_product = models.ForeignKey(
        "CatalogProduct", on_delete=models.PROTECT, related_name="invoice_lines", null=True, blank=True
    )
    service_rate = models.ForeignKey(
        ServiceRate, on_delete=models.PROTECT, related_name="invoice_lines", null=True, blank=True
    )
    contract_cost = models.ForeignKey(
        "ContractCost", on_delete=models.PROTECT, related_name="invoice_lines", null=True, blank=True
    )

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("position", "created_at", "id")
        constraints = [
            models.CheckConstraint(condition=models.Q(position__gte=1), name="invoice_line_position_positive"),
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="invoice_line_quantity_positive"),
            models.CheckConstraint(condition=models.Q(tax_rate_value__gte=0), name="invoice_line_tax_nonnegative"),
            models.CheckConstraint(
                condition=(
                    models.Q(catalog_product__isnull=True, service_rate__isnull=True)
                    | models.Q(catalog_product__isnull=True, contract_cost__isnull=True)
                    | models.Q(service_rate__isnull=True, contract_cost__isnull=True)
                ),
                name="invoice_line_one_origin",
            ),
            models.UniqueConstraint(fields=("invoice", "position"), name="invoice_line_position_unique"),
        ]
        indexes = [models.Index(fields=("tenant", "organization", "invoice"), name="core_invline_scope_idx")]

    def __str__(self) -> str:
        return self.description

    def clean(self) -> None:
        from .money import MoneyError, calculate_line, normalize_currency

        if self.invoice_id and (
            self.invoice.tenant_id != self.tenant_id or self.invoice.organization_id != self.organization_id
        ):
            raise ValidationError("Invoice line must use its invoice scope")
        origins = tuple(
            origin for origin in (self.catalog_product, self.service_rate, self.contract_cost) if origin is not None
        )
        if len(origins) > 1:
            raise ValidationError("Invoice line may retain only one origin")
        for origin in origins:
            if origin.tenant_id != self.tenant_id:
                raise ValidationError("Invoice line origin must belong to its tenant")
        contract_cost = self.contract_cost if self.contract_cost_id else None
        if contract_cost is not None and contract_cost.organization_id != self.organization_id:
            raise ValidationError("Contract cost origin must belong to the invoice Workspace")
        try:
            self.currency = normalize_currency(self.currency)
            if self.invoice_id and self.currency != self.invoice.currency:
                raise MoneyError("Invoice line currency must match the invoice currency")
            calculate_line(
                quantity=self.quantity,
                unit_amount=self.unit_amount,
                currency=self.currency,
                tax_rate=self.tax_rate_value,
                tax_inclusive=self.tax_inclusive,
            )
        except MoneyError as exc:
            raise ValidationError({"unit_amount": str(exc)}) from exc


class InstallationState(models.Model):
    """The single, migration-created installation bootstrap record."""

    SINGLETON_ID = 1

    id = models.PositiveSmallIntegerField(primary_key=True, default=SINGLETON_ID, editable=False)
    tenant = models.OneToOneField(
        Tenant,
        on_delete=models.PROTECT,
        related_name="installation_state",
        null=True,
        blank=True,
    )
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_installation",
        null=True,
        blank=True,
    )
    bootstrapped_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(id=1), name="installation_state_singleton"),
            models.CheckConstraint(
                condition=(
                    models.Q(tenant__isnull=True, owner__isnull=True, bootstrapped_at__isnull=True)
                    | models.Q(tenant__isnull=False, owner__isnull=False, bootstrapped_at__isnull=False)
                ),
                name="installation_state_complete_or_empty",
            ),
        ]

    def __str__(self) -> str:
        return "TekDocs installation state"

    @property
    def is_bootstrapped(self) -> bool:
        return self.bootstrapped_at is not None

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Installation state cannot be deleted")


class EntityVisibility(models.TextChoices):
    MSP_PRIVATE = "msp_private", "MSP private"
    CLIENT_VISIBLE = "client_visible", "Client visible"


class CredentialReferenceProvider(models.TextChoices):
    ONEPASSWORD = "onepassword", "1Password"


class WorkspaceKind(models.TextChoices):
    MSP = "msp", "MSP"
    ORGANIZATION = "organization", "Organization"


class Workspace(TimestampedModel):
    """Stable, explicit owner identity for one MSP or organization workspace."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="workspaces")
    kind = models.CharField(max_length=20, choices=WorkspaceKind.choices)
    organization = models.OneToOneField(
        "Organization",
        on_delete=models.PROTECT,
        related_name="ownership_workspace",
        null=True,
        blank=True,
    )

    objects = models.Manager()
    scoped = TenantScopedManager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(kind=WorkspaceKind.MSP, organization__isnull=True)
                    | models.Q(kind=WorkspaceKind.ORGANIZATION, organization__isnull=False)
                ),
                name="workspace_kind_owner_shape",
            ),
            models.UniqueConstraint(
                fields=("tenant",),
                condition=models.Q(kind=WorkspaceKind.MSP),
                name="one_msp_workspace_per_tenant",
            ),
        ]
        indexes = [models.Index(fields=("tenant", "kind"), name="core_workspace_tenant_kind_idx")]

    def __str__(self) -> str:
        if self.organization_id:
            return f"{self.tenant}: {self.organization}"
        return f"{self.tenant}: MSP"

    def save(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        if not self._state.adding:
            previous = Workspace.objects.only("tenant_id", "kind", "organization_id").get(pk=self.pk)
            if (
                previous.tenant_id != self.tenant_id
                or previous.kind != self.kind
                or previous.organization_id != self.organization_id
            ):
                raise ValidationError("Workspace ownership identity is immutable")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Workspace ownership identities cannot be deleted")

    def clean(self) -> None:
        organization = self.organization if self.organization_id else None
        if organization is not None and organization.tenant_id != self.tenant_id:
            raise ValidationError("Workspace organization must belong to its tenant")


def workspace_for_owner(*, tenant: Tenant, organization: "Organization | None") -> Workspace:
    if organization is None:
        return Workspace.objects.get(tenant=tenant, kind=WorkspaceKind.MSP, organization__isnull=True)
    if organization.tenant_id != tenant.id:
        raise ValidationError("Workspace organization must belong to its tenant")
    return Workspace.objects.get(tenant=tenant, kind=WorkspaceKind.ORGANIZATION, organization=organization)


class EntityManager(models.Manager["Entity"]):
    def create_owned(self, **kwargs):  # type: ignore[no-untyped-def]
        """Create an entity only after resolving its explicit owner scope."""

        tenant = kwargs.get("tenant")
        organization = kwargs.get("organization")
        if tenant is None:
            raise ValidationError("Entity creation requires an explicit tenant")
        kwargs["workspace"] = workspace_for_owner(tenant=tenant, organization=organization)
        return self.create(**kwargs)


class Entity(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="entities")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="entities")
    entity_type = models.CharField(max_length=80)
    display_name = models.CharField(max_length=240)
    custom_fields = models.JSONField(default=dict, blank=True)
    visibility = models.CharField(
        max_length=24,
        choices=EntityVisibility.choices,
        default=EntityVisibility.MSP_PRIVATE,
    )
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.PROTECT,
        related_name="scoped_entities",
        null=True,
        blank=True,
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = EntityManager()
    scoped = OrganizationScopedManager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(visibility__in=EntityVisibility.values),
                name="entity_visibility_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "entity_type"]),
            models.Index(fields=["tenant", "display_name"]),
            models.Index(fields=["tenant", "organization", "entity_type"]),
            models.Index(fields=["tenant", "organization", "visibility"]),
        ]

    def __str__(self) -> str:
        return self.display_name

    def save(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        if not self._state.adding:
            previous = Entity.objects.only("tenant_id", "workspace_id", "organization_id").get(pk=self.pk)
            if (
                previous.tenant_id != self.tenant_id
                or previous.workspace_id != self.workspace_id
                or previous.organization_id != self.organization_id
            ):
                raise ValidationError("Entity ownership identity is immutable")
        super().save(*args, **kwargs)

    def clean(self) -> None:
        organization = self.organization if self.organization_id else None
        if self.workspace_id and (
            self.workspace.tenant_id != self.tenant_id or self.workspace.organization_id != self.organization_id
        ):
            raise ValidationError("Entity workspace must match its tenant and organization scope")
        if organization is not None and self.tenant_id != organization.tenant_id:
            raise ValidationError("Organization scope must belong to the entity tenant")


class CredentialReference(TimestampedModel):
    """A scoped pointer to a credential held and revealed by an external provider."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="credential_references")
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.PROTECT,
        related_name="credential_references",
        null=True,
        blank=True,
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="credential_reference")
    provider = models.CharField(max_length=32, choices=CredentialReferenceProvider.choices)
    reference_url = models.CharField(max_length=1000)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("entity__display_name", "entity_id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(provider__in=CredentialReferenceProvider.values),
                name="credential_reference_provider_valid",
            )
        ]
        indexes = [models.Index(fields=("tenant", "organization", "archived_at"), name="core_credref_scope_idx")]

    def __str__(self) -> str:
        return self.entity.display_name

    def clean(self) -> None:
        organization = self.organization if self.organization_id else None
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Credential reference and entity scopes must match")
        if organization is not None and organization.tenant_id != self.tenant_id:
            raise ValidationError("Credential reference organization must belong to its tenant")


class CatalogProductKind(models.TextChoices):
    HARDWARE = "hardware", "Hardware"
    SOFTWARE = "software", "Software"


class CatalogModelLifecycle(models.TextChoices):
    ACTIVE = "active", "Active"
    DISCONTINUED = "discontinued", "Discontinued"
    PRE_RELEASE = "pre_release", "Pre-release"


class CatalogProduct(TimestampedModel):
    """A supplier-owned, addressable hardware or software product family."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="catalog_products")
    organization = models.ForeignKey("Organization", on_delete=models.PROTECT, related_name="catalog_products")
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="catalog_product")
    kind = models.CharField(max_length=16, choices=CatalogProductKind.choices)
    description = models.CharField(max_length=1000, blank=True)
    unit_amount = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    currency = models.CharField(max_length=3, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("entity__display_name", "entity_id")
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(unit_amount__isnull=True, currency="")
                    | models.Q(unit_amount__isnull=False) & ~models.Q(currency="")
                ),
                name="catalog_product_price_pair",
            )
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "kind", "archived_at"), name="core_catprod_scope_idx")
        ]

    def __str__(self) -> str:
        return self.entity.display_name

    def clean(self) -> None:
        from .money import MoneyError, normalize_currency, validate_amount

        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Catalog product and entity scopes must match")
        if self.organization_id and self.organization.tenant_id != self.tenant_id:
            raise ValidationError("Catalog product organization must belong to its tenant")
        if (self.unit_amount is None) != (not self.currency):
            raise ValidationError("Catalog product price and currency must be provided together")
        if self.unit_amount is not None:
            try:
                self.currency = normalize_currency(self.currency)
                validate_amount(self.unit_amount, self.currency)
            except MoneyError as exc:
                raise ValidationError({"unit_amount": str(exc)}) from exc


class CatalogSpecificationDefinition(TimestampedModel):
    """Stable supplier-owned identity for an immutable specification schema history."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="catalog_specification_definitions")
    organization = models.ForeignKey(
        "Organization", on_delete=models.PROTECT, related_name="catalog_specification_definitions"
    )
    name = models.CharField(max_length=160)
    product_kind = models.CharField(max_length=16, choices=CatalogProductKind.choices)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("tenant", "organization", "product_kind", "name"),
                name="unique_catalog_spec_definition_name",
            )
        ]
        indexes = [
            models.Index(
                fields=("tenant", "organization", "product_kind", "archived_at"),
                name="core_catspecdef_scope_idx",
            )
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding and "archived_at" not in (kwargs.get("update_fields") or ()):
            raise ValidationError("Specification-definition identity is immutable")
        return super().save(*args, **kwargs)

    def clean(self) -> None:
        if self.organization_id and self.organization.tenant_id != self.tenant_id:
            raise ValidationError("Specification definition organization must belong to its tenant")


class CatalogSpecificationDefinitionVersion(models.Model):
    """An immutable JSON Schema contract used by catalog-model revisions."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="catalog_specification_versions")
    organization = models.ForeignKey(
        "Organization", on_delete=models.PROTECT, related_name="catalog_specification_versions"
    )
    definition = models.ForeignKey(CatalogSpecificationDefinition, on_delete=models.PROTECT, related_name="versions")
    version = models.PositiveIntegerField()
    schema = models.JSONField()
    checksum = models.CharField(max_length=64)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="catalog_specification_versions",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("definition_id", "version")
        constraints = [
            models.UniqueConstraint(fields=("definition", "version"), name="unique_catalog_spec_definition_version"),
            models.CheckConstraint(condition=models.Q(version__gte=1), name="catalog_spec_version_positive"),
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "definition", "version"), name="core_catspecver_scope_idx")
        ]

    def __str__(self) -> str:
        return f"{self.definition_id} v{self.version}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ValidationError("Specification-definition versions are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Specification-definition versions are immutable")

    def clean(self) -> None:
        if self.definition_id and (
            self.definition.tenant_id != self.tenant_id or self.definition.organization_id != self.organization_id
        ):
            raise ValidationError("Specification version and definition scopes must match")


class CatalogModel(TimestampedModel):
    """A stable, addressable supplier template whose data changes through revisions."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="catalog_models")
    organization = models.ForeignKey("Organization", on_delete=models.PROTECT, related_name="catalog_models")
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="catalog_model")
    product = models.ForeignKey(CatalogProduct, on_delete=models.PROTECT, related_name="models")
    model_number = models.CharField(max_length=160)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("entity__display_name", "entity_id")
        constraints = [
            models.UniqueConstraint(
                fields=("tenant", "organization", "product", "model_number"),
                name="unique_catalog_model_number",
            )
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "product", "archived_at"), name="core_catmodel_scope_idx")
        ]

    def __str__(self) -> str:
        return self.entity.display_name

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Catalog model and entity scopes must match")
        if self.product_id and (
            self.product.tenant_id != self.tenant_id or self.product.organization_id != self.organization_id
        ):
            raise ValidationError("Catalog model and product scopes must match")


class CatalogModelRevision(models.Model):
    """Immutable model specifications pinned to one immutable schema version."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="catalog_model_revisions")
    organization = models.ForeignKey("Organization", on_delete=models.PROTECT, related_name="catalog_model_revisions")
    model = models.ForeignKey(CatalogModel, on_delete=models.PROTECT, related_name="revisions")
    parent = models.OneToOneField(
        "self", on_delete=models.PROTECT, related_name="child_revision", null=True, blank=True
    )
    revision = models.PositiveIntegerField()
    specification_version = models.ForeignKey(
        CatalogSpecificationDefinitionVersion,
        on_delete=models.PROTECT,
        related_name="model_revisions",
    )
    lifecycle = models.CharField(max_length=24, choices=CatalogModelLifecycle.choices)
    specifications = models.JSONField(default=dict)
    notes = models.CharField(max_length=1000, blank=True)
    checksum = models.CharField(max_length=64)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="catalog_model_revisions",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("model_id", "revision")
        constraints = [
            models.UniqueConstraint(fields=("model", "revision"), name="unique_catalog_model_revision"),
            models.CheckConstraint(condition=models.Q(revision__gte=1), name="catalog_model_revision_positive"),
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "model", "revision"), name="core_catmodelrev_scope_idx")
        ]

    def __str__(self) -> str:
        return f"{self.model_id} r{self.revision}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ValidationError("Catalog model revisions are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Catalog model revisions are immutable")

    def clean(self) -> None:
        if self.model_id and (
            self.model.tenant_id != self.tenant_id or self.model.organization_id != self.organization_id
        ):
            raise ValidationError("Catalog model revision and model scopes must match")
        if self.specification_version_id and (
            self.specification_version.tenant_id != self.tenant_id
            or self.specification_version.organization_id != self.organization_id
        ):
            raise ValidationError("Catalog model revision and specification scopes must match")


class CatalogProductDocument(TimestampedModel):
    """A supplier-owned association to one exact client-visible STATIC publication."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="catalog_product_documents")
    organization = models.ForeignKey("Organization", on_delete=models.PROTECT, related_name="catalog_product_documents")
    product = models.ForeignKey(CatalogProduct, on_delete=models.PROTECT, related_name="document_associations")
    model = models.ForeignKey(
        CatalogModel,
        on_delete=models.PROTECT,
        related_name="document_associations",
        null=True,
        blank=True,
    )
    publication = models.ForeignKey(
        "DocumentPublication", on_delete=models.PROTECT, related_name="catalog_associations"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="catalog_product_documents",
        null=True,
        blank=True,
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("publication__title", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("product", "publication"),
                condition=models.Q(archived_at__isnull=True, model__isnull=True),
                name="unique_active_product_document",
            ),
            models.UniqueConstraint(
                fields=("product", "model", "publication"),
                condition=models.Q(archived_at__isnull=True, model__isnull=False),
                name="unique_active_model_document",
            ),
        ]
        indexes = [
            models.Index(
                fields=("tenant", "organization", "product", "model", "archived_at"),
                name="core_catdoc_scope_idx",
            )
        ]

    def __str__(self) -> str:
        return f"{self.product_id}: {self.publication_id}"

    def clean(self) -> None:
        if self.product_id and (
            self.product.tenant_id != self.tenant_id or self.product.organization_id != self.organization_id
        ):
            raise ValidationError("Catalog document and product scopes must match")
        model = self.model if self.model_id else None
        if model is not None and (
            model.tenant_id != self.tenant_id
            or model.organization_id != self.organization_id
            or model.product_id != self.product_id
        ):
            raise ValidationError("Catalog document model must belong to its product and supplier")
        if self.publication_id and (
            self.publication.tenant_id != self.tenant_id
            or self.publication.organization_id != self.organization_id
            or self.publication.audience != PublicationAudience.CLIENT_VISIBLE
        ):
            raise ValidationError("Catalog documentation requires a client-visible supplier publication")


class ClientAsset(TimestampedModel):
    """A client-owned asset retaining the exact supplier model provenance present at creation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="client_assets")
    organization = models.ForeignKey(
        "Organization", on_delete=models.PROTECT, related_name="client_assets", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="client_asset")
    supplier = models.ForeignKey("Organization", on_delete=models.PROTECT, related_name="supplied_client_assets")
    product = models.ForeignKey(CatalogProduct, on_delete=models.PROTECT, related_name="client_assets")
    model = models.ForeignKey(CatalogModel, on_delete=models.PROTECT, related_name="client_assets")
    model_revision = models.ForeignKey(CatalogModelRevision, on_delete=models.PROTECT, related_name="client_assets")
    specification_version = models.ForeignKey(
        CatalogSpecificationDefinitionVersion,
        on_delete=models.PROTECT,
        related_name="client_assets",
    )
    specifications = models.JSONField(default=dict)
    provenance_checksum = models.CharField(max_length=64)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_client_assets",
        null=True,
        blank=True,
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("entity__display_name", "entity_id")
        indexes = [
            models.Index(fields=("tenant", "organization", "archived_at"), name="core_asset_scope_idx"),
            models.Index(fields=("tenant", "organization", "supplier"), name="core_asset_supplier_idx"),
        ]

    def __str__(self) -> str:
        return self.entity.display_name

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Client asset and entity scopes must match")
        organization = self.organization if self.organization_id else None
        if organization is not None and organization.tenant_id != self.tenant_id:
            raise ValidationError("Client asset organization must belong to its tenant")
        if self.supplier_id and self.supplier.tenant_id != self.tenant_id:
            raise ValidationError("Client asset supplier must belong to its tenant")
        if self.product_id and (
            self.product.tenant_id != self.tenant_id or self.product.organization_id != self.supplier_id
        ):
            raise ValidationError("Client asset product must belong to its retained supplier")
        if self.model_id and (
            self.model.tenant_id != self.tenant_id
            or self.model.organization_id != self.supplier_id
            or self.model.product_id != self.product_id
        ):
            raise ValidationError("Client asset model must belong to its retained product")
        if self.model_revision_id and (
            self.model_revision.tenant_id != self.tenant_id
            or self.model_revision.organization_id != self.supplier_id
            or self.model_revision.model_id != self.model_id
        ):
            raise ValidationError("Client asset revision must belong to its retained model")
        if self.specification_version_id and (
            self.specification_version_id != self.model_revision.specification_version_id
        ):
            raise ValidationError("Client asset specification version must match its retained model revision")


class HardwareLifecycleState(models.TextChoices):
    IN_STOCK = "in_stock", "In stock"
    IN_SERVICE = "in_service", "In service"
    REPAIR = "repair", "Repair"
    RETIRED = "retired", "Retired"
    DISPOSED = "disposed", "Disposed"


class HardwareAcquisitionMethod(models.TextChoices):
    PURCHASE = "purchase", "Purchase"
    LEASE = "lease", "Lease"
    RENTAL = "rental", "Rental"
    TRANSFER = "transfer", "Transfer"
    DONATION = "donation", "Donation"
    OTHER = "other", "Other"


class HardwareDisposalMethod(models.TextChoices):
    RECYCLED = "recycled", "Recycled"
    RETURNED = "returned", "Returned"
    SOLD = "sold", "Sold"
    DONATED = "donated", "Donated"
    DESTROYED = "destroyed", "Destroyed"
    LOST = "lost", "Lost"
    OTHER = "other", "Other"


class ClientHardwareAsset(TimestampedModel):
    """Mutable current-state projection for one client-owned hardware asset."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="client_hardware_assets")
    organization = models.ForeignKey(
        "Organization", on_delete=models.PROTECT, related_name="client_hardware_assets", null=True, blank=True
    )
    asset = models.OneToOneField(ClientAsset, on_delete=models.PROTECT, related_name="hardware")
    serial_number = models.CharField(max_length=160, blank=True)
    asset_tag = models.CharField(max_length=120, blank=True)
    lifecycle_state = models.CharField(
        max_length=24, choices=HardwareLifecycleState.choices, default=HardwareLifecycleState.IN_STOCK
    )
    acquired_on = models.DateField(null=True, blank=True)
    acquisition_method = models.CharField(max_length=24, choices=HardwareAcquisitionMethod.choices, blank=True)
    acquisition_reference = models.CharField(max_length=240, blank=True)
    warranty_provider = models.CharField(max_length=160, blank=True)
    warranty_starts_on = models.DateField(null=True, blank=True)
    warranty_ends_on = models.DateField(null=True, blank=True)
    warranty_reference = models.CharField(max_length=240, blank=True)
    assigned_person = models.ForeignKey(
        "PersonAssociation", on_delete=models.PROTECT, related_name="assigned_hardware", null=True, blank=True
    )
    assigned_site = models.ForeignKey(
        "Site", on_delete=models.PROTECT, related_name="assigned_hardware", null=True, blank=True
    )
    assigned_location = models.ForeignKey(
        "Location", on_delete=models.PROTECT, related_name="assigned_hardware", null=True, blank=True
    )
    assigned_at = models.DateTimeField(null=True, blank=True)
    disposed_on = models.DateField(null=True, blank=True)
    disposal_method = models.CharField(max_length=24, choices=HardwareDisposalMethod.choices, blank=True)
    disposal_reason = models.CharField(max_length=500, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(lifecycle_state__in=HardwareLifecycleState.values),
                name="hardware_state_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(acquisition_method="")
                | models.Q(acquisition_method__in=HardwareAcquisitionMethod.values),
                name="hardware_acquisition_method_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(disposal_method="") | models.Q(disposal_method__in=HardwareDisposalMethod.values),
                name="hardware_disposal_method_valid",
            ),
            models.UniqueConstraint(
                fields=("tenant", "organization", "serial_number"),
                condition=~models.Q(serial_number=""),
                name="unique_hardware_serial_in_org",
                nulls_distinct=False,
            ),
            models.UniqueConstraint(
                fields=("tenant", "organization", "asset_tag"),
                condition=~models.Q(asset_tag=""),
                name="unique_hardware_tag_in_org",
                nulls_distinct=False,
            ),
        ]
        indexes = [models.Index(fields=("tenant", "organization", "lifecycle_state"), name="core_hwasset_scope_idx")]

    def __str__(self) -> str:
        return f"Hardware profile for {self.asset_id}"

    def clean(self) -> None:
        if self.asset_id and (
            self.asset.tenant_id != self.tenant_id
            or self.asset.organization_id != self.organization_id
            or self.asset.product.kind != CatalogProductKind.HARDWARE
        ):
            raise ValidationError("Hardware profile must use an exact client hardware asset scope")
        if self.warranty_starts_on and self.warranty_ends_on and self.warranty_ends_on < self.warranty_starts_on:
            raise ValidationError("Warranty end date cannot precede its start date")
        for target in (self.assigned_person, self.assigned_site, self.assigned_location):
            if target is not None and (
                target.tenant_id != self.tenant_id or target.organization_id != self.organization_id
            ):
                raise ValidationError("Hardware assignment targets must use the asset's client scope")
        assigned_location = self.assigned_location if self.assigned_location_id else None
        if assigned_location is not None and self.assigned_site_id != assigned_location.site_id:
            raise ValidationError("Hardware assignment location must belong to its selected site")
        if self.lifecycle_state == HardwareLifecycleState.DISPOSED:
            if not self.disposed_on or not self.disposal_method:
                raise ValidationError("Disposed hardware requires a date and method")
            if self.assigned_person_id or self.assigned_site_id or self.assigned_location_id or self.assigned_at:
                raise ValidationError("Disposed hardware cannot retain a current assignment")
        elif self.disposed_on or self.disposal_method or self.disposal_reason:
            raise ValidationError("Disposal details require the disposed lifecycle state")


class HardwareLifecycleEventType(models.TextChoices):
    CREATED = "created", "Created"
    DETAILS_UPDATED = "details_updated", "Details updated"
    STATE_CHANGED = "state_changed", "State changed"
    ASSIGNED = "assigned", "Assigned"
    UNASSIGNED = "unassigned", "Unassigned"
    DISPOSED = "disposed", "Disposed"


class ClientAssetLifecycleEvent(models.Model):
    """Append-only, value-minimized history for one client hardware asset."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="client_asset_lifecycle_events")
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.PROTECT,
        related_name="client_asset_lifecycle_events",
        null=True,
        blank=True,
    )
    asset = models.ForeignKey(ClientAsset, on_delete=models.PROTECT, related_name="lifecycle_events")
    event_type = models.CharField(max_length=32, choices=HardwareLifecycleEventType.choices)
    from_state = models.CharField(max_length=24, blank=True)
    to_state = models.CharField(max_length=24, blank=True)
    person = models.ForeignKey("PersonAssociation", on_delete=models.PROTECT, null=True, blank=True)
    site = models.ForeignKey("Site", on_delete=models.PROTECT, null=True, blank=True)
    location = models.ForeignKey("Location", on_delete=models.PROTECT, null=True, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-occurred_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(event_type__in=HardwareLifecycleEventType.values),
                name="hardware_event_type_valid",
            )
        ]
        indexes = [
            models.Index(
                fields=("tenant", "organization", "asset", "occurred_at"),
                name="core_hwevent_scope_idx",
            )
        ]

    def __str__(self) -> str:
        return f"{self.asset_id}: {self.event_type}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ValidationError("Hardware lifecycle events are append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Hardware lifecycle events are append-only")

    def clean(self) -> None:
        if self.asset_id and (
            self.asset.tenant_id != self.tenant_id or self.asset.organization_id != self.organization_id
        ):
            raise ValidationError("Hardware lifecycle event must use its asset scope")
        for target in (self.person, self.site, self.location):
            if target is not None and (
                target.tenant_id != self.tenant_id or target.organization_id != self.organization_id
            ):
                raise ValidationError("Lifecycle assignment targets must use the asset's client scope")
        location = self.location if self.location_id else None
        if location is not None and self.site_id != location.site_id:
            raise ValidationError("Lifecycle event location must belong to its selected site")


class SoftwareInstallationStatus(models.TextChoices):
    PLANNED = "planned", "Planned"
    INSTALLED = "installed", "Installed"
    SUSPENDED = "suspended", "Suspended"
    UNINSTALLED = "uninstalled", "Uninstalled"


class SoftwareLicenseKind(models.TextChoices):
    SUBSCRIPTION = "subscription", "Subscription"
    PERPETUAL = "perpetual", "Perpetual"
    TRIAL = "trial", "Trial"


class SoftwareLicenseStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    EXPIRED = "expired", "Expired"
    TERMINATED = "terminated", "Terminated"


class SoftwareRenewalInterval(models.TextChoices):
    NONE = "none", "None"
    MONTHLY = "monthly", "Monthly"
    ANNUAL = "annual", "Annual"
    MULTI_YEAR = "multi_year", "Multi-year"


class ClientSoftwareInstallation(TimestampedModel):
    """Current installation state for one client-owned software asset."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="client_software_installations")
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.PROTECT,
        related_name="client_software_installations",
        null=True,
        blank=True,
    )
    asset = models.OneToOneField(ClientAsset, on_delete=models.PROTECT, related_name="software_installation")
    status = models.CharField(
        max_length=20, choices=SoftwareInstallationStatus.choices, default=SoftwareInstallationStatus.PLANNED
    )
    installed_version = models.CharField(max_length=160, blank=True)
    installed_on = models.DateField(null=True, blank=True)
    last_verified_on = models.DateField(null=True, blank=True)
    site = models.ForeignKey(
        "Site", on_delete=models.PROTECT, null=True, blank=True, related_name="software_installations"
    )

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=SoftwareInstallationStatus.values),
                name="software_installation_status_valid",
            )
        ]
        indexes = [models.Index(fields=("tenant", "organization", "status"), name="core_swinstall_scope_idx")]

    def __str__(self) -> str:
        return f"Software installation for {self.asset_id}"

    def clean(self) -> None:
        if self.asset_id and (
            self.asset.tenant_id != self.tenant_id
            or self.asset.organization_id != self.organization_id
            or self.asset.product.kind != CatalogProductKind.SOFTWARE
        ):
            raise ValidationError("Software installation must use an exact client software asset scope")
        site = self.site if self.site_id else None
        if site is not None and (site.tenant_id != self.tenant_id or site.organization_id != self.organization_id):
            raise ValidationError("Software installation site must use the asset's client scope")
        if self.status == SoftwareInstallationStatus.INSTALLED and not self.installed_on:
            raise ValidationError("Installed software requires an installation date")


class SoftwareLicense(TimestampedModel):
    """Addressable client entitlement related to one retained software product."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="software_licenses")
    organization = models.ForeignKey(
        "Organization", on_delete=models.PROTECT, related_name="software_licenses", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="software_license")
    supplier = models.ForeignKey("Organization", on_delete=models.PROTECT, related_name="supplied_software_licenses")
    product = models.ForeignKey(CatalogProduct, on_delete=models.PROTECT, related_name="software_licenses")
    model = models.ForeignKey(
        CatalogModel, on_delete=models.PROTECT, null=True, blank=True, related_name="software_licenses"
    )
    kind = models.CharField(max_length=20, choices=SoftwareLicenseKind.choices)
    status = models.CharField(
        max_length=20, choices=SoftwareLicenseStatus.choices, default=SoftwareLicenseStatus.ACTIVE
    )
    seat_limit = models.PositiveIntegerField(default=1)
    starts_on = models.DateField(null=True, blank=True)
    renews_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    renewal_interval = models.CharField(
        max_length=20, choices=SoftwareRenewalInterval.choices, default=SoftwareRenewalInterval.NONE
    )
    auto_renew = models.BooleanField(default=False)
    reference = models.CharField(max_length=240, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="software_licenses"
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(seat_limit__gte=1), name="software_license_seat_limit_positive"),
            models.CheckConstraint(
                condition=models.Q(kind__in=SoftwareLicenseKind.values), name="software_license_kind_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=SoftwareLicenseStatus.values), name="software_license_status_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(renewal_interval__in=SoftwareRenewalInterval.values),
                name="software_renewal_interval_valid",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "status", "renews_on"), name="core_swlicense_scope_idx")
        ]

    def __str__(self) -> str:
        return self.entity.display_name

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Software license and entity scopes must match")
        if self.product_id and (
            self.product.tenant_id != self.tenant_id
            or self.product.organization_id != self.supplier_id
            or self.product.kind != CatalogProductKind.SOFTWARE
        ):
            raise ValidationError("Software license requires a retained supplier software product")
        catalog_model = self.model if self.model_id else None
        if catalog_model is not None and (
            catalog_model.product_id != self.product_id or catalog_model.organization_id != self.supplier_id
        ):
            raise ValidationError("Software license model must belong to its supplier product")
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValidationError("License end date cannot precede its start date")
        if self.starts_on and self.renews_on and self.renews_on < self.starts_on:
            raise ValidationError("Renewal date cannot precede the license start date")
        if self.kind == SoftwareLicenseKind.PERPETUAL and (
            self.auto_renew or self.renewal_interval != SoftwareRenewalInterval.NONE
        ):
            raise ValidationError("Perpetual licenses cannot auto-renew or use a renewal interval")


class SoftwareLicenseInstallation(models.Model):
    """Explicit relationship between an entitlement and a covered installation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="software_license_installations")
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.PROTECT,
        related_name="software_license_installations",
        null=True,
        blank=True,
    )
    license = models.ForeignKey(SoftwareLicense, on_delete=models.PROTECT, related_name="installation_links")
    installation = models.ForeignKey(ClientSoftwareInstallation, on_delete=models.PROTECT, related_name="license_links")
    created_at = models.DateTimeField(auto_now_add=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        constraints = [models.UniqueConstraint(fields=("license", "installation"), name="unique_license_installation")]
        indexes = [models.Index(fields=("tenant", "organization", "license"), name="core_swlicinst_scope_idx")]

    def __str__(self) -> str:
        return f"{self.license_id}: {self.installation_id}"

    def clean(self) -> None:
        if (
            self.license_id
            and self.installation_id
            and (
                self.license.tenant_id != self.tenant_id
                or self.license.organization_id != self.organization_id
                or self.installation.tenant_id != self.tenant_id
                or self.installation.organization_id != self.organization_id
                or self.installation.asset.product_id != self.license.product_id
            )
        ):
            raise ValidationError("License and installation must share client scope and software product")


class SoftwareLicenseSeat(models.Model):
    """One retained seat allocation within a client entitlement."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="software_license_seats")
    organization = models.ForeignKey(
        "Organization", on_delete=models.PROTECT, related_name="software_license_seats", null=True, blank=True
    )
    license = models.ForeignKey(SoftwareLicense, on_delete=models.PROTECT, related_name="seats")
    seat_number = models.PositiveIntegerField()
    person = models.ForeignKey(
        "PersonAssociation", on_delete=models.PROTECT, null=True, blank=True, related_name="software_license_seats"
    )
    installation = models.ForeignKey(
        ClientSoftwareInstallation, on_delete=models.PROTECT, null=True, blank=True, related_name="license_seats"
    )
    assigned_at = models.DateTimeField(default=timezone.now)
    revoked_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("license", "seat_number"), name="unique_software_license_seat_number"),
            models.CheckConstraint(
                condition=models.Q(seat_number__gte=1), name="software_license_seat_number_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(person__isnull=False) | models.Q(installation__isnull=False),
                name="software_seat_has_target",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "license", "revoked_at"), name="core_swseat_scope_idx")
        ]

    def __str__(self) -> str:
        return f"{self.license_id}: seat {self.seat_number}"

    def clean(self) -> None:
        if self.license_id and (
            self.license.tenant_id != self.tenant_id or self.license.organization_id != self.organization_id
        ):
            raise ValidationError("Software seat and license scopes must match")
        for target in (self.person, self.installation):
            if target is not None and (
                target.tenant_id != self.tenant_id or target.organization_id != self.organization_id
            ):
                raise ValidationError("Software seat targets must use the license's client scope")
        installation = self.installation if self.installation_id else None
        if installation is not None and installation.asset.product_id != self.license.product_id:
            raise ValidationError("Software seat installation must use the licensed product")


class SoftwareLicenseEventType(models.TextChoices):
    CREATED = "created", "Created"
    DETAILS_UPDATED = "details_updated", "Details updated"
    INSTALLATION_LINKED = "installation_linked", "Installation linked"
    INSTALLATION_UNLINKED = "installation_unlinked", "Installation unlinked"
    SEAT_ASSIGNED = "seat_assigned", "Seat assigned"
    SEAT_REVOKED = "seat_revoked", "Seat revoked"


class SoftwareLicenseEvent(models.Model):
    """Append-only, value-minimized licensing lifecycle history."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="software_license_events")
    organization = models.ForeignKey(
        "Organization", on_delete=models.PROTECT, related_name="software_license_events", null=True, blank=True
    )
    license = models.ForeignKey(SoftwareLicense, on_delete=models.PROTECT, related_name="events")
    event_type = models.CharField(max_length=32, choices=SoftwareLicenseEventType.choices)
    installation = models.ForeignKey(ClientSoftwareInstallation, on_delete=models.PROTECT, null=True, blank=True)
    person = models.ForeignKey("PersonAssociation", on_delete=models.PROTECT, null=True, blank=True)
    seat_number = models.PositiveIntegerField(null=True, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-occurred_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(event_type__in=SoftwareLicenseEventType.values),
                name="software_license_event_type_valid",
            )
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "license", "occurred_at"), name="core_swlicevent_scope_idx")
        ]

    def __str__(self) -> str:
        return f"{self.license_id}: {self.event_type}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ValidationError("Software license events are append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Software license events are append-only")

    def clean(self) -> None:
        if self.license_id and (
            self.license.tenant_id != self.tenant_id or self.license.organization_id != self.organization_id
        ):
            raise ValidationError("Software license event must use its license scope")
        for target in (self.installation, self.person):
            if target is not None and (
                target.tenant_id != self.tenant_id or target.organization_id != self.organization_id
            ):
                raise ValidationError("Software license event targets must use its client scope")


class CommercialContractKind(models.TextChoices):
    SERVICE = "service", "Service"
    SUPPORT = "support", "Support"
    LEASE = "lease", "Lease"
    SUBSCRIPTION = "subscription", "Subscription"
    OTHER = "other", "Other"


class CommercialContractStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    EXPIRED = "expired", "Expired"
    TERMINATED = "terminated", "Terminated"


class CostBillingInterval(models.TextChoices):
    ONE_TIME = "one_time", "One time"
    MONTHLY = "monthly", "Monthly"
    QUARTERLY = "quarterly", "Quarterly"
    ANNUAL = "annual", "Annual"


class CommercialContract(TimestampedModel):
    """Client-scoped commercial agreement whose financial terms are projected separately."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="commercial_contracts")
    organization = models.ForeignKey(
        "Organization", on_delete=models.PROTECT, related_name="commercial_contracts", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="commercial_contract")
    provider = models.ForeignKey("Organization", on_delete=models.PROTECT, related_name="provided_commercial_contracts")
    kind = models.CharField(max_length=24, choices=CommercialContractKind.choices)
    status = models.CharField(
        max_length=24, choices=CommercialContractStatus.choices, default=CommercialContractStatus.DRAFT
    )
    description = models.CharField(max_length=1000, blank=True)
    reference = models.CharField(max_length=240, blank=True)
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    renews_on = models.DateField(null=True, blank=True)
    auto_renew = models.BooleanField(default=False)
    renewal_notice_days = models.PositiveSmallIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="commercial_contracts"
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("entity__display_name", "entity_id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(kind__in=CommercialContractKind.values), name="commercial_contract_kind_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=CommercialContractStatus.values),
                name="commercial_contract_status_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(renewal_notice_days__lte=3650),
                name="commercial_contract_notice_days_bounded",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "status", "renews_on"), name="core_contract_scope_idx"),
            models.Index(fields=("tenant", "organization", "provider"), name="core_contract_provider_idx"),
        ]

    def __str__(self) -> str:
        return self.entity.display_name

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id
            or self.entity.organization_id != self.organization_id
            or self.entity.entity_type != "commercial_contract"
            or self.entity.visibility != EntityVisibility.MSP_PRIVATE
        ):
            raise ValidationError("Commercial contract entity identity, scope, and visibility must match")
        organization = self.organization if self.organization_id else None
        if organization is not None and organization.tenant_id != self.tenant_id:
            raise ValidationError("Commercial contract organization must belong to its tenant")
        if self.provider_id and (self.provider.tenant_id != self.tenant_id or self.provider_id == self.organization_id):
            raise ValidationError("Commercial contract provider must be another organization in the same tenant")
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValidationError("Contract end date cannot precede its start date")
        if self.starts_on and self.renews_on and self.renews_on < self.starts_on:
            raise ValidationError("Contract renewal date cannot precede its start date")


class ContractCost(TimestampedModel):
    """A sensitive commercial line item that is never projected without costs.view."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="contract_costs")
    organization = models.ForeignKey(
        "Organization", on_delete=models.PROTECT, related_name="contract_costs", null=True, blank=True
    )
    contract = models.ForeignKey(CommercialContract, on_delete=models.PROTECT, related_name="costs")
    label = models.CharField(max_length=160)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3)
    billing_interval = models.CharField(max_length=16, choices=CostBillingInterval.choices)
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=1)
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    reference = models.CharField(max_length=240, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("label", "id")
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gte=0), name="contract_cost_amount_nonnegative"),
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="contract_cost_quantity_positive"),
            models.CheckConstraint(
                condition=models.Q(billing_interval__in=CostBillingInterval.values),
                name="contract_cost_interval_valid",
            ),
        ]
        indexes = [models.Index(fields=("tenant", "organization", "contract"), name="core_contract_cost_scope_idx")]

    def __str__(self) -> str:
        return self.label

    def clean(self) -> None:
        if self.contract_id and (
            self.contract.tenant_id != self.tenant_id or self.contract.organization_id != self.organization_id
        ):
            raise ValidationError("Contract cost must use its contract scope")
        if self.currency and (len(self.currency) != 3 or not self.currency.isascii() or not self.currency.isalpha()):
            raise ValidationError("Currency must be a three-letter currency code")
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValidationError("Cost end date cannot precede its start date")


class ClientAssetDocumentProvenance(models.Model):
    """Append-only client projection of one exact supplier STATIC publication."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="client_asset_documents")
    organization = models.ForeignKey(
        "Organization", on_delete=models.PROTECT, related_name="client_asset_documents", null=True, blank=True
    )
    asset = models.ForeignKey(ClientAsset, on_delete=models.PROTECT, related_name="document_provenance")
    catalog_document = models.ForeignKey(
        CatalogProductDocument, on_delete=models.PROTECT, related_name="client_asset_provenance"
    )
    publication = models.ForeignKey(
        "DocumentPublication", on_delete=models.PROTECT, related_name="client_asset_provenance"
    )
    content_digest = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("publication__title", "id")
        constraints = [models.UniqueConstraint(fields=("asset", "publication"), name="unique_client_asset_publication")]
        indexes = [models.Index(fields=("tenant", "organization", "asset"), name="core_assetdoc_scope_idx")]

    def __str__(self) -> str:
        return f"{self.asset_id}: {self.publication_id}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ValidationError("Client asset document provenance is append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Client asset document provenance is append-only")

    def clean(self) -> None:
        if self.asset_id and (
            self.asset.tenant_id != self.tenant_id or self.asset.organization_id != self.organization_id
        ):
            raise ValidationError("Asset document provenance must use its asset scope")
        if self.catalog_document_id and (
            self.catalog_document.tenant_id != self.tenant_id
            or self.catalog_document.organization_id != self.asset.supplier_id
            or self.catalog_document.product_id != self.asset.product_id
            or self.catalog_document.model_id not in {None, self.asset.model_id}
        ):
            raise ValidationError("Asset document provenance does not apply to the retained model")
        if self.publication_id and (
            self.publication_id != self.catalog_document.publication_id
            or self.publication.content_digest != self.content_digest
        ):
            raise ValidationError("Asset document publication identity or digest does not match")


class OrganizationAccessMode(models.TextChoices):
    ALL_AUTHORIZED = "all_authorized", "All authorized MSP staff"
    ASSIGNED_ONLY = "assigned_only", "Assigned MSP staff only"


class Organization(TimestampedModel):
    """A tenant-owned business organization anchored to one universal entity."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="organizations")
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="organization_record")
    legal_name = models.CharField(max_length=240, blank=True)
    website = models.URLField(max_length=500, blank=True)
    access_mode = models.CharField(
        max_length=32,
        choices=OrganizationAccessMode.choices,
        default=OrganizationAccessMode.ASSIGNED_ONLY,
    )

    objects = models.Manager()
    scoped = TenantScopedManager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(access_mode__in=OrganizationAccessMode.values),
                name="organization_access_mode_valid",
            )
        ]
        indexes = [
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["tenant", "access_mode", "entity"], name="core_org_tenant_access_idx"),
        ]

    def __str__(self) -> str:
        return self.entity.display_name

    def save(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        creating = self._state.adding
        with transaction.atomic():
            super().save(*args, **kwargs)
            if creating:
                Workspace.objects.create(
                    id=workspace_identity_uuid(tenant_id=self.tenant_id, organization_id=self.id),
                    tenant=self.tenant,
                    kind=WorkspaceKind.ORGANIZATION,
                    organization=self,
                )

    def clean(self) -> None:
        if self.entity_id and self.tenant_id != self.entity.tenant_id:
            raise ValidationError("Organization entity must belong to the organization tenant")
        if self.entity_id and self.entity.organization_id is not None:
            raise ValidationError("An organization anchor cannot itself be organization-scoped")


class OrganizationKind(models.TextChoices):
    CLIENT = "client", "Client"
    VENDOR = "vendor", "Vendor"
    MANUFACTURER = "manufacturer", "Manufacturer"
    PARTNER = "partner", "Partner"


class OrganizationClassification(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="organization_classifications")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="classifications")
    kind = models.CharField(max_length=32, choices=OrganizationKind.choices)

    objects = models.Manager()
    scoped = TenantScopedManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "kind"],
                name="unique_organization_classification",
            )
        ]
        indexes = [models.Index(fields=["tenant", "kind", "organization"])]

    def __str__(self) -> str:
        return f"{self.organization_id} {self.kind}"

    def clean(self) -> None:
        if self.organization_id and self.tenant_id != self.organization.tenant_id:
            raise ValidationError("Organization classification must belong to its tenant")


class Site(TimestampedModel):
    """An addressable physical or operational site in one workspace."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="sites")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="sites",
        null=True,
        blank=True,
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="site_record")
    code = models.CharField(max_length=64, blank=True)
    address_line_1 = models.CharField(max_length=240, blank=True)
    address_line_2 = models.CharField(max_length=240, blank=True)
    city = models.CharField(max_length=120, blank=True)
    region = models.CharField(max_length=120, blank=True)
    postal_code = models.CharField(max_length=32, blank=True)
    country_code = models.CharField(max_length=2, blank=True)
    timezone = models.CharField(max_length=64, blank=True)
    phone = models.CharField(max_length=64, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "organization", "code"],
                condition=~models.Q(code=""),
                name="unique_site_code_in_workspace",
                nulls_distinct=False,
            )
        ]
        indexes = [models.Index(fields=["tenant", "organization", "archived_at"])]

    def __str__(self) -> str:
        return self.entity.display_name

    def clean(self) -> None:
        organization = self.organization if self.organization_id else None
        if organization is not None and self.tenant_id != organization.tenant_id:
            raise ValidationError("Site organization must belong to its tenant")
        if self.entity_id and self.tenant_id != self.entity.tenant_id:
            raise ValidationError("Site entity must belong to the site tenant")
        if self.entity_id and self.entity.organization_id != self.organization_id:
            raise ValidationError("Site entity must use the site's workspace scope")


class LocationKind(models.TextChoices):
    BUILDING = "building", "Building"
    FLOOR = "floor", "Floor"
    SUITE = "suite", "Suite"
    ROOM = "room", "Room"
    OFFICE = "office", "Office"
    DESK = "desk", "Desk"
    AREA = "area", "Area"


class Location(TimestampedModel):
    """An addressable hierarchical place within one site."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="locations")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="locations",
        null=True,
        blank=True,
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="location_record")
    site = models.ForeignKey(Site, on_delete=models.PROTECT, related_name="locations")
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="children",
        null=True,
        blank=True,
    )
    kind = models.CharField(max_length=32, choices=LocationKind.choices)
    code = models.CharField(max_length=64, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=~models.Q(parent=models.F("id")), name="location_not_own_parent"),
            models.UniqueConstraint(
                fields=["site", "parent", "code"],
                condition=~models.Q(code=""),
                name="unique_location_code_under_parent",
                nulls_distinct=False,
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "organization", "site", "archived_at"]),
            models.Index(fields=["site", "parent", "kind"]),
        ]

    def __str__(self) -> str:
        return self.entity.display_name

    def clean(self) -> None:
        organization = self.organization if self.organization_id else None
        if organization is not None and self.tenant_id != organization.tenant_id:
            raise ValidationError("Location organization must belong to its tenant")
        if self.entity_id and self.tenant_id != self.entity.tenant_id:
            raise ValidationError("Location entity must belong to the location tenant")
        if self.entity_id and self.entity.organization_id != self.organization_id:
            raise ValidationError("Location entity must use the location's workspace scope")
        site = self.site if self.site_id else None
        if site is not None and (site.tenant_id != self.tenant_id or site.organization_id != self.organization_id):
            raise ValidationError("Location site must use the location's workspace scope")
        parent = self.parent if self.parent_id else None
        if parent is not None and (parent.site_id != self.site_id or self.parent_id == self.id):
            raise ValidationError("Location parent must be a different location in the same site")


class CustomFieldType(models.TextChoices):
    TEXT = "text", "Text"
    INTEGER = "integer", "Integer"
    NUMBER = "number", "Number"
    BOOLEAN = "boolean", "Boolean"
    DATE = "date", "Date"
    URL = "url", "URL"
    EMAIL = "email", "Email"
    CHOICE = "choice", "Choice"
    MULTI_CHOICE = "multi_choice", "Multiple choice"


class CustomFieldDefinition(TimestampedModel):
    """Stable identity and ownership for a versioned custom field."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="custom_field_definitions")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="custom_field_definitions",
        null=True,
        blank=True,
    )
    key = models.SlugField(max_length=80)
    entity_type = models.CharField(max_length=80)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = TenantScopedManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "organization", "entity_type", "key"],
                name="unique_custom_field_key_in_scope",
                nulls_distinct=False,
            )
        ]
        indexes = [
            models.Index(
                fields=["tenant", "organization", "entity_type", "archived_at"],
                name="core_cfdef_scope_idx",
            )
        ]

    def __str__(self) -> str:
        return f"{self.entity_type}.{self.key}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self._state.adding is False:
            raise ValidationError("Custom-field definitions change only through versioning and archival services")
        return super().save(*args, **kwargs)

    def clean(self) -> None:
        organization = self.organization if self.organization_id else None
        if organization is not None and organization.tenant_id != self.tenant_id:
            raise ValidationError("Custom-field organization must belong to its tenant")


class CustomFieldDefinitionVersion(models.Model):
    """Immutable validation and presentation contract for one definition revision."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="custom_field_definition_versions")
    definition = models.ForeignKey(CustomFieldDefinition, on_delete=models.PROTECT, related_name="versions")
    version = models.PositiveIntegerField()
    label = models.CharField(max_length=160)
    description = models.CharField(max_length=500, blank=True)
    required = models.BooleanField(default=False)
    field_type = models.CharField(max_length=32, choices=CustomFieldType.choices)
    schema = models.JSONField()
    display_order = models.IntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="custom_field_definition_versions",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = TenantScopedManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["definition", "version"], name="unique_custom_field_definition_version"),
            models.CheckConstraint(condition=models.Q(version__gte=1), name="custom_field_version_positive"),
        ]
        ordering = ("definition_id", "version")

    def __str__(self) -> str:
        return f"{self.definition_id} v{self.version}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self._state.adding is False:
            raise ValidationError("Custom-field definition versions are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Custom-field definition versions are immutable")

    def clean(self) -> None:
        if self.definition_id and self.definition.tenant_id != self.tenant_id:
            raise ValidationError("Custom-field version must belong to the definition tenant")


class Person(TimestampedModel):
    """One tenant-wide human identity anchored to the entity registry."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="people")
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="person_record")
    preferred_name = models.CharField(max_length=160, blank=True)
    phone = models.CharField(max_length=64, blank=True)
    email = models.EmailField(max_length=254, blank=True)

    objects = models.Manager()
    scoped = TenantScopedManager()

    class Meta:
        indexes = [models.Index(fields=["tenant", "created_at"])]

    def __str__(self) -> str:
        return self.entity.display_name

    def clean(self) -> None:
        if self.entity_id and self.tenant_id != self.entity.tenant_id:
            raise ValidationError("Person entity must belong to the person tenant")
        if self.entity_id and self.entity.organization_id is not None:
            raise ValidationError("A person identity must remain tenant-scoped")


class PersonAssociationKind(models.TextChoices):
    EMPLOYEE = "employee", "Employee"
    CONTACT = "contact", "Contact"


class PersonAssociation(TimestampedModel):
    """A person's employment or contact role in one explicit workspace."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="person_associations")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="person_associations",
        null=True,
        blank=True,
    )
    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="associations")
    kind = models.CharField(max_length=32, choices=PersonAssociationKind.choices)
    role = models.CharField(max_length=160, blank=True)
    responsibility = models.CharField(max_length=240, blank=True)
    location = models.CharField(max_length=160, blank=True)
    office = models.CharField(max_length=120, blank=True)
    site = models.ForeignKey(
        Site,
        on_delete=models.PROTECT,
        related_name="person_associations",
        null=True,
        blank=True,
    )
    structured_location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        related_name="person_associations",
        null=True,
        blank=True,
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["person", "organization"],
                condition=models.Q(organization__isnull=False),
                name="unique_person_organization_association",
            ),
            models.UniqueConstraint(
                fields=["person"],
                condition=models.Q(organization__isnull=True),
                name="unique_person_msp_association",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "organization", "archived_at"]),
            models.Index(fields=["tenant", "kind", "organization"]),
        ]

    def __str__(self) -> str:
        return f"{self.person_id} in {self.organization_id or 'MSP'}"

    def clean(self) -> None:
        if self.person_id and self.tenant_id != self.person.tenant_id:
            raise ValidationError("Person association must belong to the person tenant")
        organization = self.organization if self.organization_id else None
        if organization is not None and self.tenant_id != organization.tenant_id:
            raise ValidationError("Person association organization must belong to its tenant")
        site = self.site if self.site_id else None
        if site is not None and (site.tenant_id != self.tenant_id or site.organization_id != self.organization_id):
            raise ValidationError("Person association site must use its workspace scope")
        structured_location = self.structured_location if self.structured_location_id else None
        if structured_location is not None:
            if self.site_id != structured_location.site_id:
                raise ValidationError("Person association location must belong to its selected site")
            if (
                structured_location.tenant_id != self.tenant_id
                or structured_location.organization_id != self.organization_id
            ):
                raise ValidationError("Person association location must use its workspace scope")


class NetworkRackStatus(models.TextChoices):
    PLANNED = "planned", "Planned"
    ACTIVE = "active", "Active"
    RETIRED = "retired", "Retired"


class NetworkRack(TimestampedModel):
    """An addressable equipment rack in one exact physical Workspace location."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="network_racks")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="network_racks", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="network_rack")
    site = models.ForeignKey(Site, on_delete=models.PROTECT, related_name="network_racks")
    location = models.ForeignKey(
        Location, on_delete=models.PROTECT, related_name="network_racks", null=True, blank=True
    )
    unit_count = models.PositiveSmallIntegerField(default=42)
    status = models.CharField(max_length=16, choices=NetworkRackStatus.choices, default=NetworkRackStatus.ACTIVE)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("entity__display_name", "entity_id")
        constraints = [
            models.CheckConstraint(condition=models.Q(unit_count__gte=1, unit_count__lte=100), name="rack_units_valid"),
            models.CheckConstraint(condition=models.Q(status__in=NetworkRackStatus.values), name="rack_status_valid"),
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "site"), name="core_netrack_scope_idx"),
        ]

    def __str__(self) -> str:
        return self.entity.display_name

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Network rack and entity scopes must match")
        if self.site_id and (
            self.site.tenant_id != self.tenant_id or self.site.organization_id != self.organization_id
        ):
            raise ValidationError("Network rack site must use its Workspace scope")
        location = self.location if self.location_id else None
        if location is not None and (
            location.tenant_id != self.tenant_id
            or location.organization_id != self.organization_id
            or location.site_id != self.site_id
        ):
            raise ValidationError("Network rack location must belong to its selected site and Workspace")


class NetworkDeviceRole(models.TextChoices):
    ROUTER = "router", "Router"
    SWITCH = "switch", "Switch"
    FIREWALL = "firewall", "Firewall"
    WIRELESS_CONTROLLER = "wireless_controller", "Wireless controller"
    ACCESS_POINT = "access_point", "Access point"
    LOAD_BALANCER = "load_balancer", "Load balancer"
    OTHER = "other", "Other"


class NetworkDeviceStatus(models.TextChoices):
    PLANNED = "planned", "Planned"
    ACTIVE = "active", "Active"
    OFFLINE = "offline", "Offline"
    RETIRED = "retired", "Retired"


class NetworkDevice(TimestampedModel):
    """A network role and physical placement backed by one hardware asset.

    ``legacy_unbacked`` exists only to preserve pre-0.4.9 rows whose original
    creation preceded the asset requirement. New application records may not set it.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="network_devices")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="network_devices", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="network_device")
    role = models.CharField(max_length=32, choices=NetworkDeviceRole.choices)
    status = models.CharField(max_length=16, choices=NetworkDeviceStatus.choices, default=NetworkDeviceStatus.ACTIVE)
    hardware_asset = models.OneToOneField(
        ClientAsset,
        on_delete=models.PROTECT,
        related_name="network_device",
        null=True,
        blank=True,
    )
    legacy_unbacked = models.BooleanField(default=False)
    site = models.ForeignKey(Site, on_delete=models.PROTECT, related_name="network_devices", null=True, blank=True)
    location = models.ForeignKey(
        Location, on_delete=models.PROTECT, related_name="network_devices", null=True, blank=True
    )
    rack = models.ForeignKey(
        NetworkRack, on_delete=models.PROTECT, related_name="network_devices", null=True, blank=True
    )
    rack_unit = models.PositiveSmallIntegerField(null=True, blank=True)
    rack_units = models.PositiveSmallIntegerField(default=1)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("entity__display_name", "entity_id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(role__in=NetworkDeviceRole.values), name="network_device_role_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=NetworkDeviceStatus.values), name="network_device_status_valid"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(rack__isnull=True, rack_unit__isnull=True, rack_units=1)
                    | models.Q(rack__isnull=False, rack_unit__isnull=False, rack_units__gte=1, rack_units__lte=100)
                ),
                name="network_device_rack_placement_complete",
            ),
            models.CheckConstraint(
                condition=models.Q(location__isnull=True) | models.Q(site__isnull=False),
                name="network_device_location_requires_site",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "role"), name="core_netdevice_scope_idx"),
            models.Index(fields=("rack", "rack_unit"), name="core_netdevice_rack_idx"),
        ]

    def __str__(self) -> str:
        return self.entity.display_name

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Network device and entity scopes must match")
        hardware_asset = self.hardware_asset if self.hardware_asset_id else None
        if hardware_asset is not None and (
            hardware_asset.tenant_id != self.tenant_id
            or hardware_asset.organization_id != self.organization_id
            or hardware_asset.product.kind != CatalogProductKind.HARDWARE
        ):
            raise ValidationError("Network device hardware asset must be hardware in the same Workspace")
        if hardware_asset is None and not self.legacy_unbacked:
            raise ValidationError("Network devices require a hardware asset")
        if hardware_asset is not None and self.legacy_unbacked:
            raise ValidationError("Asset-backed network devices cannot retain the legacy marker")
        site = self.site if self.site_id else None
        if site is not None and (site.tenant_id != self.tenant_id or site.organization_id != self.organization_id):
            raise ValidationError("Network device site must use its Workspace scope")
        location = self.location if self.location_id else None
        if location is not None and (
            location.tenant_id != self.tenant_id
            or location.organization_id != self.organization_id
            or location.site_id != self.site_id
        ):
            raise ValidationError("Network device location must belong to its selected site and Workspace")
        rack = self.rack if self.rack_id else None
        if rack is not None and (
            rack.tenant_id != self.tenant_id
            or rack.organization_id != self.organization_id
            or rack.site_id != self.site_id
            or rack.location_id != self.location_id
        ):
            raise ValidationError("Network device rack must match its physical Workspace location")


class NetworkVRF(TimestampedModel):
    """An isolated routing namespace in one exact Workspace."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="network_vrfs")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="network_vrfs", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="network_vrf")
    route_distinguisher = models.CharField(max_length=64, blank=True)
    description = models.TextField(blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("entity__display_name", "entity_id")
        indexes = [models.Index(fields=("tenant", "organization"), name="core_netvrf_scope_idx")]

    def __str__(self) -> str:
        return self.entity.display_name

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Network VRF and entity scopes must match")


class NetworkVLAN(TimestampedModel):
    """A VLAN identifier owned by one exact Workspace."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="network_vlans")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="network_vlans", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="network_vlan")
    vlan_id = models.PositiveSmallIntegerField()
    description = models.TextField(blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("vlan_id", "entity__display_name", "entity_id")
        constraints = [
            models.CheckConstraint(condition=models.Q(vlan_id__gte=1, vlan_id__lte=4094), name="network_vlan_id_valid"),
            models.UniqueConstraint(
                fields=("tenant", "organization", "vlan_id"),
                name="network_vlan_id_unique_in_workspace",
                nulls_distinct=False,
            ),
        ]
        indexes = [models.Index(fields=("tenant", "organization", "vlan_id"), name="core_netvlan_scope_idx")]

    def __str__(self) -> str:
        return f"{self.vlan_id} · {self.entity.display_name}"

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Network VLAN and entity scopes must match")


class NetworkSubnet(TimestampedModel):
    """A user-facing network record retained on the original subnet table for compatibility."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="network_subnets")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="network_subnets", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="network_subnet")
    cidr = models.CharField(max_length=49)
    address_family = models.PositiveSmallIntegerField()
    vrf = models.ForeignKey(NetworkVRF, on_delete=models.PROTECT, related_name="subnets", null=True, blank=True)
    vlan = models.ForeignKey(NetworkVLAN, on_delete=models.PROTECT, related_name="subnets", null=True, blank=True)
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="networks", null=True, blank=True)
    vlan_number = models.PositiveSmallIntegerField(null=True, blank=True)
    use_full_range = models.BooleanField(default=True)
    assignable_start = models.GenericIPAddressField(null=True, blank=True)
    assignable_end = models.GenericIPAddressField(null=True, blank=True)
    primary_dns = models.GenericIPAddressField(null=True, blank=True)
    secondary_dns = models.GenericIPAddressField(null=True, blank=True)
    description = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("address_family", "cidr", "entity_id")
        constraints = [
            models.CheckConstraint(condition=models.Q(address_family__in=(4, 6)), name="network_subnet_family_valid"),
            models.CheckConstraint(
                condition=models.Q(vlan_number__isnull=True) | models.Q(vlan_number__gte=1, vlan_number__lte=4094),
                name="network_record_vlan_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(use_full_range=True, assignable_start__isnull=True, assignable_end__isnull=True)
                    | models.Q(use_full_range=False, assignable_start__isnull=False, assignable_end__isnull=False)
                ),
                name="network_record_range_mode_valid",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "vrf"), name="core_netsubnet_scope_idx"),
            models.Index(fields=("tenant", "organization", "cidr"), name="core_netsubnet_cidr_idx"),
        ]

    def __str__(self) -> str:
        return self.cidr

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Network subnet and entity scopes must match")
        for related, label in (
            (self.vrf if self.vrf_id else None, "VRF"),
            (self.vlan if self.vlan_id else None, "VLAN"),
            (self.location if self.location_id else None, "location"),
        ):
            if related is not None and (
                related.tenant_id != self.tenant_id or related.organization_id != self.organization_id
            ):
                raise ValidationError(f"Network subnet {label} must use its Workspace scope")


class NetworkInterfaceKind(models.TextChoices):
    PHYSICAL = "physical", "Physical"
    VIRTUAL = "virtual", "Virtual"
    LAG = "lag", "Link aggregation"
    LOOPBACK = "loopback", "Loopback"
    TUNNEL = "tunnel", "Tunnel"
    WIRELESS = "wireless", "Wireless"
    OTHER = "other", "Other"


class NetworkInterfaceStatus(models.TextChoices):
    PLANNED = "planned", "Planned"
    ACTIVE = "active", "Active"
    DISABLED = "disabled", "Disabled"
    RETIRED = "retired", "Retired"


class NetworkInterface(TimestampedModel):
    """A stable logical or physical interface on one network device."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="network_interfaces")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="network_interfaces", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="network_interface")
    device = models.ForeignKey(NetworkDevice, on_delete=models.PROTECT, related_name="interfaces")
    kind = models.CharField(max_length=24, choices=NetworkInterfaceKind.choices)
    status = models.CharField(max_length=24, choices=NetworkInterfaceStatus.choices)
    description = models.TextField(blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("device__entity__display_name", "entity__display_name", "entity_id")
        indexes = [models.Index(fields=("tenant", "organization", "device"), name="core_netif_scope_idx")]

    def __str__(self) -> str:
        return f"{self.device.entity.display_name} · {self.entity.display_name}"

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Network interface and entity scopes must match")
        if self.device_id and (
            self.device.tenant_id != self.tenant_id or self.device.organization_id != self.organization_id
        ):
            raise ValidationError("Network interface device must use its Workspace scope")


class NetworkIPAddressStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    RESERVED = "reserved", "Reserved"
    DHCP = "dhcp", "DHCP"
    DEPRECATED = "deprecated", "Deprecated"


class NetworkIPAddress(TimestampedModel):
    """A canonical host address within one subnet and routing namespace."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="network_ip_addresses")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="network_ip_addresses", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="network_ip_address")
    subnet = models.ForeignKey(NetworkSubnet, on_delete=models.PROTECT, related_name="ip_addresses")
    interface = models.ForeignKey(
        NetworkInterface, on_delete=models.PROTECT, related_name="ip_addresses", null=True, blank=True
    )
    hardware_asset = models.ForeignKey(
        ClientAsset, on_delete=models.PROTECT, related_name="network_ip_addresses", null=True, blank=True
    )
    address = models.CharField(max_length=45)
    address_family = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=24, choices=NetworkIPAddressStatus.choices)
    dns_name = models.CharField(max_length=253, blank=True)
    description = models.TextField(blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("address_family", "address", "entity_id")
        constraints = [
            models.CheckConstraint(condition=models.Q(address_family__in=(4, 6)), name="network_ip_family_valid")
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "subnet"), name="core_netip_scope_idx"),
            models.Index(fields=("tenant", "organization", "address"), name="core_netip_address_idx"),
            models.Index(fields=("tenant", "organization", "hardware_asset"), name="core_netip_asset_idx"),
        ]

    def __str__(self) -> str:
        return self.address

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Network IP address and entity scopes must match")
        for related, label in (
            (self.subnet if self.subnet_id else None, "subnet"),
            (self.interface if self.interface_id else None, "interface"),
            (self.hardware_asset if self.hardware_asset_id else None, "hardware asset"),
        ):
            if related is not None and (
                related.tenant_id != self.tenant_id or related.organization_id != self.organization_id
            ):
                raise ValidationError(f"Network IP address {label} must use its Workspace scope")
        hardware_asset = self.hardware_asset if self.hardware_asset_id else None
        if hardware_asset is not None and hardware_asset.product.kind != CatalogProductKind.HARDWARE:
            raise ValidationError("Network IP address assignment requires a hardware asset")
        interface = self.interface if self.interface_id else None
        if interface is not None and hardware_asset is not None:
            interface_asset_id = interface.device.hardware_asset_id
            if interface_asset_id is not None and interface_asset_id != hardware_asset.id:
                raise ValidationError("Network IP address legacy interface and hardware asset must agree")


class NetworkMACAddress(TimestampedModel):
    """A canonical EUI-48 address assigned directly to hardware or retained legacy interface data."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="network_mac_addresses")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="network_mac_addresses", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="network_mac_address")
    interface = models.ForeignKey(
        NetworkInterface, on_delete=models.PROTECT, related_name="mac_addresses", null=True, blank=True
    )
    hardware_asset = models.ForeignKey(
        ClientAsset, on_delete=models.PROTECT, related_name="network_mac_addresses", null=True, blank=True
    )
    address = models.CharField(max_length=17)
    description = models.TextField(blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("address", "entity_id")
        constraints = [
            models.UniqueConstraint(
                fields=("tenant", "organization", "address"),
                name="network_mac_unique_in_workspace",
                nulls_distinct=False,
            )
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "interface"), name="core_netmac_scope_idx"),
            models.Index(fields=("tenant", "organization", "hardware_asset"), name="core_netmac_asset_idx"),
        ]

    def __str__(self) -> str:
        return self.address

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Network MAC address and entity scopes must match")
        if (
            self.interface_id
            and self.interface is not None
            and (self.interface.tenant_id != self.tenant_id or self.interface.organization_id != self.organization_id)
        ):
            raise ValidationError("Network MAC address interface must use its Workspace scope")
        hardware_asset = self.hardware_asset if self.hardware_asset_id else None
        if hardware_asset is not None and (
            hardware_asset.tenant_id != self.tenant_id
            or hardware_asset.organization_id != self.organization_id
            or hardware_asset.product.kind != CatalogProductKind.HARDWARE
        ):
            raise ValidationError("Network MAC address assignment requires same-Workspace hardware")
        interface = self.interface if self.interface_id else None
        if interface is not None and hardware_asset is not None:
            interface_asset_id = interface.device.hardware_asset_id
            if interface_asset_id is not None and interface_asset_id != hardware_asset.id:
                raise ValidationError("Network MAC address legacy interface and hardware asset must agree")


class NetBoxObjectType(models.TextChoices):
    RACK = "dcim.rack", "Rack"
    DEVICE = "dcim.device", "Device"
    MAC_ADDRESS = "dcim.macaddress", "MAC address"
    VLAN = "ipam.vlan", "VLAN"
    PREFIX = "ipam.prefix", "Prefix"
    IP_ADDRESS = "ipam.ipaddress", "IP address"


class NetBoxReference(TimestampedModel):
    """A stable NetBox identity attached to one lightweight TekDocs record."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="netbox_references")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="netbox_references")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="netbox_references", null=True, blank=True
    )
    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="netbox_references")
    object_type = models.CharField(max_length=32, choices=NetBoxObjectType.choices)
    object_id = models.PositiveBigIntegerField()
    observed_fingerprint = models.CharField(max_length=64, blank=True)
    last_observed_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("object_type", "object_id", "id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(object_type__in=NetBoxObjectType.values), name="netbox_type_valid"
            ),
            models.CheckConstraint(condition=models.Q(object_id__gte=1), name="netbox_object_id_positive"),
            models.CheckConstraint(
                condition=models.Q(observed_fingerprint="") | models.Q(observed_fingerprint__regex=r"^[0-9a-f]{64}$"),
                name="netbox_fingerprint_valid",
            ),
            models.UniqueConstraint(
                fields=("workspace", "entity"),
                condition=models.Q(archived_at__isnull=True),
                name="netbox_active_entity_unique",
            ),
            models.UniqueConstraint(
                fields=("workspace", "object_type", "object_id"),
                condition=models.Q(archived_at__isnull=True),
                name="netbox_active_remote_unique",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "archived_at"), name="core_netbox_scope_idx"),
            models.Index(fields=("workspace", "object_type", "object_id"), name="core_netbox_remote_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.object_type}:{self.object_id}"

    def clean(self) -> None:
        if self.workspace_id and (
            self.workspace.tenant_id != self.tenant_id or self.workspace.organization_id != self.organization_id
        ):
            raise ValidationError("NetBox reference Workspace ownership does not match")
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id
            or self.entity.workspace_id != self.workspace_id
            or self.entity.organization_id != self.organization_id
            or self.entity.archived_at is not None
        ):
            raise ValidationError("NetBox reference entity must use its active Workspace scope")


class NetworkCircuitKind(models.TextChoices):
    INTERNET = "internet", "Internet"
    WAN = "wan", "WAN"
    MPLS = "mpls", "MPLS"
    DARK_FIBER = "dark_fiber", "Dark fiber"
    BROADBAND = "broadband", "Broadband"
    CELLULAR = "cellular", "Cellular"
    VOICE = "voice", "Voice"
    OTHER = "other", "Other"


class NetworkCircuitStatus(models.TextChoices):
    ORDERED = "ordered", "Ordered"
    PROVISIONING = "provisioning", "Provisioning"
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    DISCONNECTED = "disconnected", "Disconnected"


class NetworkCircuit(TimestampedModel):
    """A provider service with exact Workspace ownership and optional contract provenance."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="network_circuits")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="network_circuits", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="network_circuit")
    provider = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="provided_network_circuits")
    contract = models.ForeignKey(
        CommercialContract, on_delete=models.PROTECT, related_name="network_circuits", null=True, blank=True
    )
    service_identifier = models.CharField(max_length=240)
    kind = models.CharField(max_length=24, choices=NetworkCircuitKind.choices)
    status = models.CharField(max_length=24, choices=NetworkCircuitStatus.choices)
    bandwidth_down_mbps = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    bandwidth_up_mbps = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    installed_on = models.DateField(null=True, blank=True)
    service_starts_on = models.DateField(null=True, blank=True)
    review_on = models.DateField(null=True, blank=True)
    planned_disconnect_on = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("entity__display_name", "entity_id")
        constraints = [
            models.CheckConstraint(condition=models.Q(kind__in=NetworkCircuitKind.values), name="circuit_kind_valid"),
            models.CheckConstraint(
                condition=models.Q(status__in=NetworkCircuitStatus.values), name="circuit_status_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(bandwidth_down_mbps__isnull=True) | models.Q(bandwidth_down_mbps__gt=0),
                name="circuit_down_bandwidth_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(bandwidth_up_mbps__isnull=True) | models.Q(bandwidth_up_mbps__gt=0),
                name="circuit_up_bandwidth_positive",
            ),
            models.UniqueConstraint(
                fields=("tenant", "organization", "provider", "service_identifier"),
                name="circuit_service_id_unique",
                nulls_distinct=False,
            ),
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "status"), name="core_circuit_scope_idx"),
            models.Index(fields=("tenant", "organization", "provider"), name="core_circuit_provider_idx"),
            models.Index(fields=("tenant", "organization", "review_on"), name="core_circuit_review_idx"),
        ]

    def __str__(self) -> str:
        return self.entity.display_name

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id
            or self.entity.organization_id != self.organization_id
            or self.entity.entity_type != "network_circuit"
        ):
            raise ValidationError("Network circuit entity identity and scope must match")
        if self.provider_id and (self.provider.tenant_id != self.tenant_id or self.provider_id == self.organization_id):
            raise ValidationError("Network circuit provider must be another organization in the same tenant")
        if not self.service_identifier.strip():
            raise ValidationError("Network circuit service identifier is required")
        contract = self.contract if self.contract_id else None
        if contract is not None and (
            contract.tenant_id != self.tenant_id
            or contract.organization_id != self.organization_id
            or contract.provider_id != self.provider_id
            or contract.archived_at is not None
        ):
            raise ValidationError("Network circuit contract must use the same Workspace and provider")
        if (
            self.service_starts_on
            and self.planned_disconnect_on
            and self.planned_disconnect_on < self.service_starts_on
        ):
            raise ValidationError("Circuit disconnect date cannot precede its service start date")


class NetworkHandoffSide(models.TextChoices):
    A = "a", "A side"
    Z = "z", "Z side"


class NetworkHandoffMedia(models.TextChoices):
    COPPER = "copper", "Copper"
    FIBER = "fiber", "Fiber"
    COAX = "coax", "Coax"
    WIRELESS = "wireless", "Wireless"
    VIRTUAL = "virtual", "Virtual"
    OTHER = "other", "Other"


class NetworkCircuitHandoff(TimestampedModel):
    """One physical or logical demarcation for a retained circuit."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="network_circuit_handoffs")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="network_circuit_handoffs", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="network_circuit_handoff")
    circuit = models.ForeignKey(NetworkCircuit, on_delete=models.PROTECT, related_name="handoffs")
    side = models.CharField(max_length=1, choices=NetworkHandoffSide.choices)
    media = models.CharField(max_length=16, choices=NetworkHandoffMedia.choices)
    connector = models.CharField(max_length=120, blank=True)
    provider_reference = models.CharField(max_length=240, blank=True)
    site = models.ForeignKey(
        Site, on_delete=models.PROTECT, related_name="network_circuit_handoffs", null=True, blank=True
    )
    location = models.ForeignKey(
        Location, on_delete=models.PROTECT, related_name="network_circuit_handoffs", null=True, blank=True
    )
    device = models.ForeignKey(
        NetworkDevice, on_delete=models.PROTECT, related_name="network_circuit_handoffs", null=True, blank=True
    )
    interface = models.ForeignKey(
        NetworkInterface, on_delete=models.PROTECT, related_name="network_circuit_handoffs", null=True, blank=True
    )
    description = models.TextField(blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("circuit__entity__display_name", "side", "entity__display_name", "entity_id")
        constraints = [
            models.CheckConstraint(condition=models.Q(side__in=NetworkHandoffSide.values), name="handoff_side_valid"),
            models.CheckConstraint(
                condition=models.Q(media__in=NetworkHandoffMedia.values), name="handoff_media_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(location__isnull=True) | models.Q(site__isnull=False),
                name="handoff_location_requires_site",
            ),
            models.CheckConstraint(
                condition=models.Q(interface__isnull=True) | models.Q(device__isnull=False),
                name="handoff_interface_requires_device",
            ),
            models.UniqueConstraint(fields=("circuit", "side", "entity"), name="handoff_identity_unique"),
            models.UniqueConstraint(
                fields=("interface",),
                condition=models.Q(interface__isnull=False),
                name="handoff_interface_unique",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "circuit"), name="core_handoff_scope_idx"),
            models.Index(fields=("tenant", "organization", "interface"), name="core_handoff_interface_idx"),
        ]

    def __str__(self) -> str:
        return self.entity.display_name

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id
            or self.entity.organization_id != self.organization_id
            or self.entity.entity_type != "network_circuit_handoff"
        ):
            raise ValidationError("Circuit handoff entity identity and scope must match")
        for related, label in (
            (self.circuit if self.circuit_id else None, "circuit"),
            (self.site if self.site_id else None, "site"),
            (self.location if self.location_id else None, "location"),
            (self.device if self.device_id else None, "device"),
            (self.interface if self.interface_id else None, "interface"),
        ):
            if related is not None and (
                related.tenant_id != self.tenant_id or related.organization_id != self.organization_id
            ):
                raise ValidationError(f"Circuit handoff {label} must use its Workspace scope")
        if self.location_id and self.location is not None and self.location.site_id != self.site_id:
            raise ValidationError("Circuit handoff location must belong to its selected site")
        if self.interface_id and self.interface is not None and self.interface.device_id != self.device_id:
            raise ValidationError("Circuit handoff interface must belong to its selected device")
        if (
            self.device_id
            and self.site_id
            and self.device is not None
            and self.device.site_id not in (None, self.site_id)
        ):
            raise ValidationError("Circuit handoff device placement contradicts its selected site")


class WirelessNetworkPurpose(models.TextChoices):
    CORPORATE = "corporate", "Corporate"
    GUEST = "guest", "Guest"
    IOT = "iot", "IoT"
    VOICE = "voice", "Voice"
    OTHER = "other", "Other"


class WirelessNetworkSecurity(models.TextChoices):
    OPEN = "open", "Open"
    OWE = "owe", "Enhanced open (OWE)"
    WPA2_PERSONAL = "wpa2_personal", "WPA2 Personal"
    WPA3_PERSONAL = "wpa3_personal", "WPA3 Personal"
    WPA2_ENTERPRISE = "wpa2_enterprise", "WPA2 Enterprise"
    WPA3_ENTERPRISE = "wpa3_enterprise", "WPA3 Enterprise"
    MIXED_PERSONAL = "mixed_personal", "WPA2/WPA3 Personal"
    MIXED_ENTERPRISE = "mixed_enterprise", "WPA2/WPA3 Enterprise"


class WirelessNetworkStatus(models.TextChoices):
    PLANNED = "planned", "Planned"
    ACTIVE = "active", "Active"
    DISABLED = "disabled", "Disabled"
    RETIRED = "retired", "Retired"


class WirelessNetwork(TimestampedModel):
    """A logical SSID and its non-secret security posture in one exact Workspace."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="wireless_networks")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="wireless_networks", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="wireless_network")
    ssid = models.CharField(max_length=128)
    purpose = models.CharField(max_length=16, choices=WirelessNetworkPurpose.choices)
    security = models.CharField(max_length=32, choices=WirelessNetworkSecurity.choices)
    status = models.CharField(max_length=16, choices=WirelessNetworkStatus.choices)
    hidden = models.BooleanField(default=False)
    client_isolation = models.BooleanField(default=False)
    site = models.ForeignKey(Site, on_delete=models.PROTECT, related_name="wireless_networks", null=True, blank=True)
    vlan = models.ForeignKey(
        NetworkVLAN, on_delete=models.PROTECT, related_name="wireless_networks", null=True, blank=True
    )
    subnet = models.ForeignKey(
        NetworkSubnet, on_delete=models.PROTECT, related_name="wireless_networks", null=True, blank=True
    )
    description = models.TextField(blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("ssid", "site_id", "entity_id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(purpose__in=WirelessNetworkPurpose.values), name="wifi_purpose_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(security__in=WirelessNetworkSecurity.values), name="wifi_security_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=WirelessNetworkStatus.values), name="wifi_status_valid"
            ),
            models.UniqueConstraint(
                fields=("tenant", "organization", "site", "ssid"),
                name="wifi_ssid_unique_in_site",
                nulls_distinct=False,
            ),
        ]
        indexes = [models.Index(fields=("tenant", "organization", "status"), name="core_wifi_scope_idx")]

    def __str__(self) -> str:
        return self.ssid

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Wireless network and entity scopes must match")
        if not self.ssid or len(self.ssid.encode("utf-8")) > 32:
            raise ValidationError("SSID must contain between 1 and 32 UTF-8 bytes")
        for related, label in (
            (self.site if self.site_id else None, "site"),
            (self.vlan if self.vlan_id else None, "VLAN"),
            (self.subnet if self.subnet_id else None, "subnet"),
        ):
            if related is not None and (
                related.tenant_id != self.tenant_id or related.organization_id != self.organization_id
            ):
                raise ValidationError(f"Wireless network {label} must use its Workspace scope")
        if self.vlan_id and self.subnet_id and self.subnet is not None and self.subnet.vlan_id != self.vlan_id:
            raise ValidationError("Wireless network subnet must belong to the selected VLAN")


class DNSZone(TimestampedModel):
    """An inventoried DNS zone; TekDocs does not query or serve it."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="dns_zones")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="dns_zones", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="dns_zone")
    name = models.CharField(max_length=253)
    description = models.TextField(blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("name", "entity_id")
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                "tenant",
                "organization",
                name="dns_zone_name_unique_in_workspace",
                nulls_distinct=False,
            )
        ]
        indexes = [models.Index(fields=("tenant", "organization", "name"), name="core_dnszone_scope_idx")]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("DNS zone and entity scopes must match")


class DNSRecordType(models.TextChoices):
    A = "A", "A"
    AAAA = "AAAA", "AAAA"
    CNAME = "CNAME", "CNAME"
    MX = "MX", "MX"
    TXT = "TXT", "TXT"
    SRV = "SRV", "SRV"
    CAA = "CAA", "CAA"
    NS = "NS", "NS"
    PTR = "PTR", "PTR"


class DNSRecord(TimestampedModel):
    """A type-validated DNS record protected by the exact Workspace network policy."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="dns_records")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="dns_records", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="dns_record")
    zone = models.ForeignKey(DNSZone, on_delete=models.PROTECT, related_name="records")
    owner_name = models.CharField(max_length=253)
    record_type = models.CharField(max_length=8, choices=DNSRecordType.choices)
    value = models.TextField()
    ttl = models.PositiveIntegerField(default=3600)
    priority = models.PositiveSmallIntegerField(null=True, blank=True)
    weight = models.PositiveSmallIntegerField(null=True, blank=True)
    port = models.PositiveSmallIntegerField(null=True, blank=True)
    ip_address = models.ForeignKey(
        NetworkIPAddress, on_delete=models.PROTECT, related_name="dns_records", null=True, blank=True
    )
    description = models.TextField(blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("zone__name", "owner_name", "record_type", "value", "entity_id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(record_type__in=DNSRecordType.values), name="dns_record_type_valid"
            ),
            models.CheckConstraint(condition=models.Q(ttl__lte=2147483647), name="dns_record_ttl_valid"),
            models.UniqueConstraint(
                fields=("zone", "owner_name", "record_type", "value", "priority", "weight", "port"),
                name="dns_record_value_unique",
                nulls_distinct=False,
            ),
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "zone"), name="core_dnsrecord_scope_idx"),
            models.Index(fields=("zone", "owner_name"), name="core_dnsrecord_owner_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.owner_name} {self.record_type}"

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("DNS record and entity scopes must match")
        for related, label in (
            (self.zone if self.zone_id else None, "zone"),
            (self.ip_address if self.ip_address_id else None, "IP address"),
        ):
            if related is not None and (
                related.tenant_id != self.tenant_id or related.organization_id != self.organization_id
            ):
                raise ValidationError(f"DNS record {label} must use its Workspace scope")


class EntityLinkType(models.TextChoices):
    RELATED_TO = "related_to", "Related to"
    CONNECTED_TO = "connected_to", "Connected to"
    DEPENDS_ON = "depends_on", "Depends on"
    MANAGED_BY = "managed_by", "Managed by"
    SUPPLIED_BY = "supplied_by", "Supplied by"
    MANUFACTURED_BY = "manufactured_by", "Manufactured by"
    PARTNERED_WITH = "partnered_with", "Partnered with"
    LOCATED_AT = "located_at", "Located at"
    ASSIGNED_TO = "assigned_to", "Assigned to"
    REFERENCES = "references", "References"


class EntityLink(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="entity_links")
    source = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="outgoing_links")
    target = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="incoming_links")
    link_type = models.CharField(max_length=80, choices=EntityLinkType.choices)
    metadata = models.JSONField(default=dict, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = TenantScopedManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "target", "link_type"],
                condition=models.Q(archived_at__isnull=True),
                name="unique_active_typed_entity_link",
            ),
            models.CheckConstraint(condition=~models.Q(source=models.F("target")), name="entity_link_not_self"),
            models.CheckConstraint(
                condition=models.Q(link_type__in=EntityLinkType.values),
                name="entity_link_type_supported",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "link_type", "archived_at"], name="entity_link_type_active_idx"),
            models.Index(fields=["tenant", "source", "archived_at"], name="entity_link_source_active_idx"),
            models.Index(fields=["tenant", "target", "archived_at"], name="entity_link_target_active_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.source_id} {self.link_type} {self.target_id}"

    def clean(self) -> None:
        if self.source_id and self.tenant_id != self.source.tenant_id:
            raise ValidationError("Source entity must belong to the link tenant")
        if self.target_id and self.tenant_id != self.target.tenant_id:
            raise ValidationError("Target entity must belong to the link tenant")
        if self.metadata != {}:
            raise ValidationError("Entity-link metadata is not accepted by this release")


class DocumentCategory(models.TextChoices):
    GENERAL = "general", "General"
    POLICY = "policy", "Policy"
    PROCEDURE = "procedure", "Procedure"
    GUIDE = "guide", "Guide"
    REFERENCE = "reference", "Reference"


class DocumentReviewState(models.TextChoices):
    UNREVIEWED = "unreviewed", "Unreviewed"
    PENDING = "pending", "Pending review"
    APPROVED = "approved", "Approved"
    CHANGES_REQUESTED = "changes_requested", "Changes requested"


class Document(TimestampedModel):
    """A Markdown document owned by exactly one MSP or organization workspace."""

    matching_excerpt: str = ""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="documents")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="documents", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="document_record")
    category = models.CharField(
        max_length=20,
        choices=DocumentCategory.choices,
        default=DocumentCategory.GENERAL,
    )
    is_template = models.BooleanField(default=False)
    library_visible = models.BooleanField(default=False)
    collection = models.CharField(max_length=120, blank=True)
    tags = models.JSONField(default=list, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_documents",
        null=True,
        blank=True,
    )
    review_due_on = models.DateField(null=True, blank=True)
    review_state = models.CharField(
        max_length=24,
        choices=DocumentReviewState.choices,
        default=DocumentReviewState.UNREVIEWED,
    )
    review_requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="requested_document_reviews",
        null=True,
        blank=True,
    )
    review_requested_at = models.DateTimeField(null=True, blank=True)
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assigned_document_reviews",
        null=True,
        blank=True,
    )
    review_decided_at = models.DateTimeField(null=True, blank=True)
    last_reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reviewed_documents",
        null=True,
        blank=True,
    )
    last_reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=500, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(category__in=DocumentCategory.values),
                name="document_category_supported",
            ),
            models.CheckConstraint(
                condition=models.Q(review_state__in=DocumentReviewState.values),
                name="document_review_state_supported",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        review_state=DocumentReviewState.PENDING,
                        review_requested_by__isnull=False,
                        review_requested_at__isnull=False,
                        reviewer__isnull=False,
                        review_decided_at__isnull=True,
                    )
                    | ~models.Q(review_state=DocumentReviewState.PENDING)
                ),
                name="document_pending_review_shape",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "organization", "archived_at"]),
            models.Index(
                fields=["tenant", "organization", "category", "is_template", "archived_at"],
                name="core_doc_category_template_idx",
            ),
            models.Index(
                fields=["tenant", "organization", "review_state", "review_due_on"],
                name="core_doc_review_health_idx",
            ),
            models.Index(
                fields=["tenant", "organization", "collection", "archived_at"],
                name="core_doc_collection_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.entity.display_name

    @property
    def health_status(self) -> str:
        if self.owner_id is None:
            return "unowned"
        if self.review_state == DocumentReviewState.CHANGES_REQUESTED:
            return "changes_requested"
        if self.review_due_on is not None and self.review_due_on <= timezone.localdate():
            return "stale"
        if self.review_state == DocumentReviewState.PENDING:
            return "pending"
        if self.review_state == DocumentReviewState.UNREVIEWED:
            return "unreviewed"
        if self.last_reviewed_at is None:
            return "unreviewed"
        return "current"

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Document entity must use the document workspace scope")


class DocumentTemplateRevision(TimestampedModel):
    """An immutable composition manifest for one MSP-owned reusable template."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="document_template_revisions")
    template = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="template_revisions")
    revision_number = models.PositiveIntegerField()
    manifest = models.JSONField(default=dict)
    checksum = models.CharField(max_length=64)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="document_template_revisions",
    )

    objects = models.Manager()
    scoped = TenantScopedManager()

    class Meta:
        ordering = ("template_id", "revision_number")
        constraints = [
            models.UniqueConstraint(fields=["template", "revision_number"], name="unique_template_revision_number"),
            models.UniqueConstraint(fields=["template", "checksum"], name="unique_template_revision_checksum"),
        ]
        indexes = [models.Index(fields=["tenant", "template", "revision_number"], name="core_tplrev_lookup_idx")]

    def __str__(self) -> str:
        return f"{self.template_id} template revision {self.revision_number}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self._state.adding is False:
            raise ValidationError("Template revisions are append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Template revisions are append-only")


class DocumentTemplateEnrollment(TimestampedModel):
    """Tracks a client document created from an MSP template and its controlled rollout state."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="document_template_enrollments")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="document_template_enrollments",
    )
    source_template = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="template_enrollments")
    destination_document = models.OneToOneField(
        Document,
        on_delete=models.PROTECT,
        related_name="template_enrollment",
    )
    applied_revision = models.ForeignKey(
        DocumentTemplateRevision,
        on_delete=models.PROTECT,
        related_name="enrollments",
    )
    placement_map = models.JSONField(default=list)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_document_template_enrollments",
    )
    last_applied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="applied_document_template_enrollments",
    )
    last_applied_at = models.DateTimeField(default=timezone.now)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        indexes = [
            models.Index(
                fields=["tenant", "organization", "source_template", "archived_at"],
                name="core_tplenroll_scope_idx",
            )
        ]

    def __str__(self) -> str:
        return f"{self.source_template_id} enrolled for {self.organization_id}"

    def clean(self) -> None:
        if self.organization_id and self.organization.tenant_id != self.tenant_id:
            raise ValidationError("Template enrollment organization must belong to its tenant")
        if self.source_template_id and (
            self.source_template.tenant_id != self.tenant_id or self.source_template.organization_id is not None
        ):
            raise ValidationError("Template enrollment source must be an MSP-owned document")
        if self.destination_document_id and (
            self.destination_document.tenant_id != self.tenant_id
            or self.destination_document.organization_id != self.organization_id
        ):
            raise ValidationError("Template enrollment destination must belong to its client organization")
        if self.applied_revision_id and self.applied_revision.template_id != self.source_template_id:
            raise ValidationError("Applied template revision must belong to the source template")


class DocumentSourceKind(models.TextChoices):
    MARKDOWN = "markdown", "Markdown"
    HTML = "html", "HTML"
    AUTO = "auto", "Automatic"


class DocumentRemoteSource(TimestampedModel):
    """A public HTTPS source monitored for one workspace-owned document."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="document_remote_sources")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="document_remote_sources", null=True, blank=True
    )
    document = models.OneToOneField(Document, on_delete=models.PROTECT, related_name="remote_source")
    url = models.URLField(max_length=500)
    source_kind = models.CharField(max_length=12, choices=DocumentSourceKind.choices, default=DocumentSourceKind.AUTO)
    enabled = models.BooleanField(default=True)
    check_interval_minutes = models.PositiveIntegerField(default=1440)
    next_check_at = models.DateTimeField(default=timezone.now)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_applied_observation = models.ForeignKey(
        "DocumentRemoteObservation",
        on_delete=models.PROTECT,
        related_name="applied_to_sources",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_document_remote_sources"
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        indexes = [
            models.Index(fields=("tenant", "organization", "enabled", "next_check_at"), name="core_docsource_due_idx")
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(check_interval_minutes__gte=15, check_interval_minutes__lte=10080),
                name="document_source_interval_bounded",
            )
        ]

    def __str__(self) -> str:
        return f"Remote source for {self.document_id}"


class DocumentRemoteObservation(models.Model):
    """Immutable, bounded evidence from one remote-source fetch."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="document_remote_observations")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="document_remote_observations", null=True, blank=True
    )
    source = models.ForeignKey(DocumentRemoteSource, on_delete=models.PROTECT, related_name="observations")
    state = models.CharField(
        max_length=16,
        choices=(("unchanged", "Unchanged"), ("changed", "Changed"), ("failed", "Failed")),
    )
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    content_type = models.CharField(max_length=120, blank=True)
    etag_digest = models.CharField(max_length=64, blank=True)
    last_modified_digest = models.CharField(max_length=64, blank=True)
    content_digest = models.CharField(max_length=64, blank=True)
    canonical_markdown = models.TextField(blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    fetched_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-fetched_at", "id")
        indexes = [models.Index(fields=("source", "fetched_at"), name="core_docobservation_idx")]

    def __str__(self) -> str:
        return f"{self.source_id} observed at {self.fetched_at}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ValidationError("Remote document observations are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Remote document observations are retained")


def document_attachment_upload_to(instance: "DocumentAttachment", _filename: str) -> str:
    """Return an opaque storage key that never includes an authored filename."""

    return str(
        PurePosixPath("document-attachments") / str(instance.tenant_id) / str(instance.document_id) / str(instance.id)
    )


def publication_artifact_upload_to(instance: "DocumentPublicationArtifact", _filename: str) -> str:
    """Return an opaque retained-artifact key without authored path material."""

    return str(
        PurePosixPath("publication-artifacts")
        / str(instance.tenant_id)
        / str(instance.publication_id)
        / str(instance.id)
    )


class DocumentAttachmentPurpose(models.TextChoices):
    ATTACHMENT = "attachment", "Attachment"
    PRIMARY_FILE = "primary_file", "Primary document file"


class DocumentAttachment(TimestampedModel):
    """A private managed file owned by exactly one document."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="document_attachments")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="document_attachments",
        null=True,
        blank=True,
    )
    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="attachments")
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="document_attachment_record")
    file = models.FileField(upload_to=document_attachment_upload_to, max_length=500)
    original_filename = models.CharField(max_length=240)
    media_type = models.CharField(max_length=120)
    size = models.PositiveBigIntegerField()
    checksum = models.CharField(max_length=64)
    storage_provider = models.CharField(max_length=80, default="django-default")
    scan_status = models.CharField(max_length=20, default="clean")
    scan_engine = models.CharField(max_length=120, default="legacy-validation")
    scanned_at = models.DateTimeField(default=timezone.now)
    purpose = models.CharField(
        max_length=20,
        choices=DocumentAttachmentPurpose.choices,
        default=DocumentAttachmentPurpose.ATTACHMENT,
    )
    version_number = models.PositiveIntegerField(null=True, blank=True)
    replaces = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        related_name="replacement",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="document_attachments",
        null=True,
        blank=True,
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(scan_status="clean"), name="document_attachment_clean_only"),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        purpose=DocumentAttachmentPurpose.ATTACHMENT,
                        version_number__isnull=True,
                        replaces__isnull=True,
                    )
                    | models.Q(
                        purpose=DocumentAttachmentPurpose.PRIMARY_FILE,
                        version_number__isnull=False,
                    )
                ),
                name="document_attachment_purpose_version",
            ),
            models.UniqueConstraint(
                fields=("document", "version_number"),
                condition=models.Q(purpose=DocumentAttachmentPurpose.PRIMARY_FILE),
                name="unique_document_primary_file_version",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "organization", "document", "archived_at"],
                name="core_docatt_scope_idx",
            ),
            models.Index(fields=["document", "checksum"], name="core_docatt_checksum_idx"),
            models.Index(
                fields=["document", "purpose", "version_number"],
                name="core_docatt_primary_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.original_filename

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            stored_purpose = type(self).objects.filter(pk=self.pk).values_list("purpose", flat=True).first()
            if stored_purpose == DocumentAttachmentPurpose.PRIMARY_FILE or (
                stored_purpose is not None and stored_purpose != self.purpose
            ):
                raise ValidationError("Primary document file versions are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self.purpose == DocumentAttachmentPurpose.PRIMARY_FILE:
            raise ValidationError("Primary document file versions are immutable")
        return super().delete(*args, **kwargs)

    def clean(self) -> None:
        if self.document_id and (
            self.document.tenant_id != self.tenant_id or self.document.organization_id != self.organization_id
        ):
            raise ValidationError("Attachment must use its document workspace scope")
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Attachment entity must use the attachment workspace scope")
        if self.scan_status != "clean" or not self.scan_engine or not self.storage_provider or not self.scanned_at:
            raise ValidationError("Only clean, scanned attachments may enter managed storage")
        if self.purpose == DocumentAttachmentPurpose.PRIMARY_FILE:
            if self.version_number is None:
                raise ValidationError("Primary document files require a version number")
            if self.version_number == 1 and self.replaces_id is not None:
                raise ValidationError("The first primary document file version cannot replace another file")
            if self.version_number > 1 and self.replaces_id is None:
                raise ValidationError("Replacement primary document files require their prior version")
            replaced = self.replaces if self.replaces_id else None
            if replaced is not None and (
                replaced.document_id != self.document_id
                or replaced.tenant_id != self.tenant_id
                or replaced.organization_id != self.organization_id
                or replaced.purpose != DocumentAttachmentPurpose.PRIMARY_FILE
                or replaced.version_number != self.version_number - 1
            ):
                raise ValidationError("Primary document file versions must form one ordered document-local chain")


class PublicationAudience(models.TextChoices):
    MSP_INTERNAL = "msp_internal", "MSP internal"
    CLIENT_VISIBLE = "client_visible", "Client visible"


class PublicationRetention(models.TextChoices):
    PERMANENT = "permanent", "Permanent"
    REVIEW_ON = "review_on", "Review on date"


class PublicationArtifactKind(models.TextChoices):
    PDF = "pdf", "PDF"
    ATTACHMENT = "attachment", "Retained attachment"
    DIAGRAM_SVG = "diagram_svg", "Diagram SVG"
    DIAGRAM_PNG = "diagram_png", "Diagram PNG"


class PublicationControlAction(models.TextChoices):
    SUBMITTED = "submitted", "Submitted"
    APPROVED = "approved", "Approved"
    WITHDRAWN = "withdrawn", "Withdrawn"


class DocumentPublication(models.Model):
    """An append-only STATIC snapshot of one document and its resolved dependencies."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="document_publications")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="document_publications",
        null=True,
        blank=True,
    )
    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="publications")
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="document_publication_record")
    title = models.CharField(max_length=240)
    category = models.CharField(max_length=20, choices=DocumentCategory.choices)
    reason = models.CharField(max_length=500)
    audience = models.CharField(max_length=24, choices=PublicationAudience.choices)
    retention = models.CharField(max_length=20, choices=PublicationRetention.choices)
    retention_review_on = models.DateField(null=True, blank=True)
    supersedes = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="successors",
        null=True,
        blank=True,
    )
    canonical_markdown = models.TextField(blank=True)
    sanitized_html = models.TextField(blank=True)
    manifest = models.JSONField()
    content_digest = models.CharField(max_length=64)
    signature = models.TextField()
    signature_algorithm = models.CharField(max_length=20, default="Ed25519")
    public_key = models.TextField()
    key_fingerprint = models.CharField(max_length=64)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="document_publications",
        null=True,
        blank=True,
    )
    published_at = models.DateTimeField()

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-published_at", "id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(audience__in=PublicationAudience.values), name="publication_audience_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(retention__in=PublicationRetention.values), name="publication_retention_valid"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(retention=PublicationRetention.PERMANENT, retention_review_on__isnull=True)
                    | models.Q(retention=PublicationRetention.REVIEW_ON, retention_review_on__isnull=False)
                ),
                name="publication_retention_date_valid",
            ),
            models.CheckConstraint(
                condition=(models.Q(audience=PublicationAudience.MSP_INTERNAL) | models.Q(organization__isnull=False)),
                name="publication_client_audience_scoped",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "organization", "document", "published_at"],
                name="core_docpub_scope_idx",
            ),
            models.Index(fields=["document", "content_digest"], name="core_docpub_digest_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.title} — {self.published_at.isoformat()}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self._state.adding is False:
            raise ValidationError("Document publications are append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Document publications are append-only")

    def clean(self) -> None:
        if self.document_id and (
            self.document.tenant_id != self.tenant_id or self.document.organization_id != self.organization_id
        ):
            raise ValidationError("Publication must use its source document workspace scope")
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Publication entity must use the publication workspace scope")
        if self.entity_id and self.entity.entity_type != "document_publication":
            raise ValidationError("Publication entity must use the document_publication type")
        if not isinstance(self.manifest, dict) or self.manifest.get("format") not in {
            "tekdocs-static-publication/v1",
            "tekdocs-static-publication/v2",
            "tekdocs-static-publication/v3",
            "tekdocs-static-publication/v4",
        }:
            raise ValidationError("Publication manifest format is invalid")
        expected_identity = {
            "publication_id": str(self.id),
            "publication_entity_id": str(self.entity_id),
            "source_document_id": str(self.document.entity_id) if self.document_id else "",
        }
        if any(self.manifest.get(key) != value for key, value in expected_identity.items()):
            raise ValidationError("Publication manifest identity does not match the publication")
        workspace = self.manifest.get("workspace")
        organization = self.organization if self.organization_id else None
        expected_workspace = {
            "kind": "organization" if self.organization_id else "msp",
            "id": str(organization.entity_id) if organization is not None else None,
        }
        if workspace != expected_workspace:
            raise ValidationError("Publication manifest workspace does not match the publication")
        if not self.reason.strip() or len(self.reason) > 500:
            raise ValidationError("Publication reason is required and may not exceed 500 characters")
        if self.audience == PublicationAudience.CLIENT_VISIBLE and self.organization_id is None:
            raise ValidationError("Client-visible publications require an organization workspace")
        if (self.retention == PublicationRetention.REVIEW_ON) != (self.retention_review_on is not None):
            raise ValidationError("Publication retention date does not match its retention class")
        supersedes = self.supersedes if self.supersedes_id else None
        if supersedes is not None and (
            supersedes.tenant_id != self.tenant_id
            or supersedes.organization_id != self.organization_id
            or supersedes.document_id != self.document_id
            or supersedes.audience != self.audience
        ):
            raise ValidationError("A correction may supersede only a publication of the same document and workspace")
        if self.manifest.get("format") in {
            "tekdocs-static-publication/v2",
            "tekdocs-static-publication/v3",
            "tekdocs-static-publication/v4",
        }:
            expected_lifecycle = {
                "reason": self.reason,
                "audience": self.audience,
                "retention": self.retention,
                "retention_review_on": self.retention_review_on.isoformat() if self.retention_review_on else None,
                "supersedes_id": str(supersedes.entity_id) if supersedes is not None else None,
            }
            if any(self.manifest.get(key) != value for key, value in expected_lifecycle.items()):
                raise ValidationError("Publication manifest lifecycle metadata does not match the publication")
        if self.manifest.get("format") in {
            "tekdocs-static-publication/v3",
            "tekdocs-static-publication/v4",
        }:
            key_resolutions = self.manifest.get("key_resolutions")
            if not isinstance(key_resolutions, list):
                raise ValidationError("Publication key resolutions are invalid")
            expressions: list[str] = []
            required = {
                "kind",
                "expression",
                "value",
                "source_entity_id",
                "source_entity_type",
                "source_fingerprint",
                "provenance",
                "resolved_at",
                "source_revision_id",
                "source_revision_number",
                "dependency_chain",
            }
            for resolution in key_resolutions:
                if not isinstance(resolution, dict) or set(resolution) != required:
                    raise ValidationError("Publication key resolutions are invalid")
                string_fields = required - {"source_revision_id", "source_revision_number", "dependency_chain"}
                if not all(isinstance(resolution[key], str) for key in string_fields):
                    raise ValidationError("Publication key resolutions are invalid")
                if (
                    resolution["kind"] not in {"field", "content"}
                    or not resolution["expression"]
                    or not resolution["value"]
                    or re.fullmatch(r"[0-9a-f]{64}", resolution["source_fingerprint"]) is None
                    or resolution["provenance"] not in {"local", "observed"}
                    or resolution["resolved_at"] != self.manifest.get("published_at")
                ):
                    raise ValidationError("Publication key resolutions are invalid")
                revision_id = resolution["source_revision_id"]
                revision_number = resolution["source_revision_number"]
                dependency_chain = resolution["dependency_chain"]
                if not isinstance(dependency_chain, list) or not all(
                    isinstance(item, str) for item in dependency_chain
                ):
                    raise ValidationError("Publication key resolutions are invalid")
                if resolution["kind"] == "field" and (
                    revision_id is not None or revision_number is not None or dependency_chain
                ):
                    raise ValidationError("Field-key revision metadata is invalid")
                if resolution["kind"] == "content" and (
                    not isinstance(revision_id, str)
                    or not isinstance(revision_number, int)
                    or revision_number < 1
                    or not dependency_chain
                ):
                    raise ValidationError("Content-key revision metadata is invalid")
                expressions.append(resolution["expression"])
            if expressions != sorted(set(expressions)):
                raise ValidationError("Publication key resolutions must be unique and ordered")
        if self.manifest.get("format") == "tekdocs-static-publication/v4":
            placements = self.manifest.get("placements")
            if not isinstance(placements, list) or not placements:
                raise ValidationError("Publication placements are invalid")
            allowed_profiles = {PlacementAudienceProfile.SHARED, self.audience}
            if any(
                not isinstance(placement, dict) or placement.get("audience_profile") not in allowed_profiles
                for placement in placements
            ):
                raise ValidationError("Publication placement audiences are invalid")

    @property
    def lifecycle_state(self) -> str:
        actions = self.control_actions
        if PublicationControlAction.WITHDRAWN in actions:
            return "withdrawn"
        if PublicationControlAction.APPROVED not in actions:
            return "pending_approval"
        successors = list(getattr(self, "prefetched_successors", ()))
        if not successors:
            successors = list(self.successors.all())
        if any(PublicationControlAction.APPROVED in successor.control_actions for successor in successors):
            return "superseded"
        if self.retention_review_on is not None and self.retention_review_on <= timezone.localdate():
            return "review_due"
        return "published"

    @property
    def control_actions(self) -> frozenset[str]:
        events = list(getattr(self, "prefetched_control_events", ()))
        if not events:
            events = list(self.control_events.all())
        return frozenset(event.action for event in events)

    @property
    def superseded_by_publication(self) -> "DocumentPublication | None":
        successors = list(getattr(self, "prefetched_successors", ()))
        if not successors:
            successors = list(self.successors.all())
        return next(
            (successor for successor in successors if PublicationControlAction.APPROVED in successor.control_actions),
            None,
        )


class DocumentPublicationControlEvent(models.Model):
    """An append-only distribution decision for one immutable STATIC publication."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="document_publication_events")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="document_publication_events",
        null=True,
        blank=True,
    )
    publication = models.ForeignKey(
        DocumentPublication,
        on_delete=models.PROTECT,
        related_name="control_events",
    )
    action = models.CharField(max_length=20, choices=PublicationControlAction.choices)
    reason = models.CharField(max_length=500)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="document_publication_control_events",
        null=True,
        blank=True,
    )
    occurred_at = models.DateTimeField(default=timezone.now)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("occurred_at", "id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(action__in=PublicationControlAction.values),
                name="publication_control_action_valid",
            ),
            models.UniqueConstraint(
                fields=("publication", "action"),
                name="unique_publication_control_action",
            ),
        ]
        indexes = [
            models.Index(
                fields=("tenant", "organization", "publication", "occurred_at"),
                name="core_pubctl_scope_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.publication_id}: {self.action}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self._state.adding is False:
            raise ValidationError("Publication control events are append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Publication control events are append-only")

    def clean(self) -> None:
        if self.publication_id and (
            self.publication.tenant_id != self.tenant_id or self.publication.organization_id != self.organization_id
        ):
            raise ValidationError("Publication control event must use its publication workspace scope")
        if not self.reason.strip() or len(self.reason) > 500:
            raise ValidationError("Publication control reason is required and may not exceed 500 characters")


class DocumentPublicationArtifact(models.Model):
    """An append-only retained byte artifact belonging to a STATIC publication."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="document_publication_artifacts")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="document_publication_artifacts",
        null=True,
        blank=True,
    )
    publication = models.ForeignKey(DocumentPublication, on_delete=models.PROTECT, related_name="artifacts")
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="document_publication_artifact")
    kind = models.CharField(max_length=20, choices=PublicationArtifactKind.choices)
    source_attachment = models.ForeignKey(
        DocumentAttachment,
        on_delete=models.PROTECT,
        related_name="publication_artifacts",
        null=True,
        blank=True,
    )
    file = models.FileField(upload_to=publication_artifact_upload_to, max_length=500)
    original_filename = models.CharField(max_length=240)
    media_type = models.CharField(max_length=120)
    size = models.PositiveBigIntegerField()
    checksum = models.CharField(max_length=64)
    created_at = models.DateTimeField()

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("kind", "original_filename", "id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(kind__in=PublicationArtifactKind.values), name="publication_artifact_kind_valid"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        kind__in=(
                            PublicationArtifactKind.PDF,
                            PublicationArtifactKind.DIAGRAM_SVG,
                            PublicationArtifactKind.DIAGRAM_PNG,
                        ),
                        source_attachment__isnull=True,
                    )
                    | models.Q(kind=PublicationArtifactKind.ATTACHMENT, source_attachment__isnull=False)
                ),
                name="publication_artifact_source_valid",
            ),
            models.UniqueConstraint(
                fields=("publication", "kind"),
                condition=models.Q(kind=PublicationArtifactKind.PDF),
                name="one_pdf_per_publication",
            ),
            models.UniqueConstraint(
                fields=("publication", "source_attachment"),
                condition=models.Q(source_attachment__isnull=False),
                name="one_retained_source_attachment",
            ),
        ]
        indexes = [models.Index(fields=("tenant", "organization", "publication"), name="core_pubart_scope_idx")]

    def __str__(self) -> str:
        return f"{self.publication.title}: {self.original_filename}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self._state.adding is False:
            raise ValidationError("Publication artifacts are append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Publication artifacts are append-only")

    def clean(self) -> None:
        if self.publication_id and (
            self.publication.tenant_id != self.tenant_id or self.publication.organization_id != self.organization_id
        ):
            raise ValidationError("Publication artifact must use its publication workspace scope")
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id
            or self.entity.organization_id != self.organization_id
            or self.entity.entity_type != "document_publication_artifact"
        ):
            raise ValidationError("Publication artifact entity scope or type is invalid")
        if (
            self.kind
            in {
                PublicationArtifactKind.PDF,
                PublicationArtifactKind.DIAGRAM_SVG,
                PublicationArtifactKind.DIAGRAM_PNG,
            }
            and self.source_attachment_id is not None
        ):
            raise ValidationError("Generated artifacts cannot identify a source attachment")
        if self.kind == PublicationArtifactKind.ATTACHMENT and self.source_attachment_id is None:
            raise ValidationError("Retained attachment artifacts require a source attachment")
        source_attachment = self.source_attachment if self.source_attachment_id else None
        if source_attachment is not None and source_attachment.document_id != self.publication.document_id:
            raise ValidationError("Retained attachment must belong to the source document")


class BlockKind(models.TextChoices):
    RICH_TEXT = "rich_text", "Rich text"
    HEADING = "heading", "Heading"
    CODE = "code", "Code"
    URL = "url", "URL"
    DOCUMENT_LINK = "document_link", "Document link"
    ENTITY_REFERENCE = "entity_reference", "Entity reference"
    FILE_REFERENCE = "file_reference", "File reference"


class Block(TimestampedModel):
    """A stable addressable content block whose content is an immutable revision chain."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="blocks")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="blocks", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="block_record")
    source_document = models.ForeignKey(
        Document,
        on_delete=models.PROTECT,
        related_name="owned_blocks",
        null=True,
        blank=True,
    )
    kind = models.CharField(max_length=32, choices=BlockKind.choices, default=BlockKind.RICH_TEXT)
    library_visible = models.BooleanField(default=False)
    current_revision = models.ForeignKey(
        "BlockRevision",
        on_delete=models.PROTECT,
        related_name="current_for_blocks",
        null=True,
        blank=True,
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(kind__in=BlockKind.values), name="document_block_kind_valid")
        ]
        indexes = [
            models.Index(fields=["tenant", "organization", "archived_at"]),
            models.Index(fields=["tenant", "organization", "kind", "archived_at"], name="core_block_kind_scope_idx"),
        ]

    def __str__(self) -> str:
        return str(self.entity_id)

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id
            or self.entity.organization_id != self.organization_id
            or self.entity.entity_type != "document_block"
        ):
            raise ValidationError("Block entity scope or type is invalid")
        source_document = self.source_document if self.source_document_id else None
        if source_document is not None and (
            source_document.tenant_id != self.tenant_id or source_document.organization_id != self.organization_id
        ):
            raise ValidationError("Block source document must use the block workspace scope")


class BlockRevision(models.Model):
    """Append-only canonical Markdown for one stable block."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="block_revisions")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="block_revisions", null=True, blank=True
    )
    block = models.ForeignKey(Block, on_delete=models.PROTECT, related_name="revisions")
    parent = models.ForeignKey("self", on_delete=models.PROTECT, related_name="children", null=True, blank=True)
    revision_number = models.PositiveIntegerField()
    markdown = models.TextField(blank=True)
    checksum = models.CharField(max_length=64)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="block_revisions",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-revision_number", "-created_at", "id")
        constraints = [
            models.UniqueConstraint(fields=["block", "revision_number"], name="unique_block_revision_number"),
            models.CheckConstraint(condition=models.Q(revision_number__gte=1), name="block_revision_number_positive"),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "organization", "block", "-revision_number"],
                name="core_blockr_tenant__42e5a8_idx",
            ),
            models.Index(fields=["block", "checksum"], name="core_blockr_block_i_a9954b_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.block_id} revision {self.revision_number}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self._state.adding is False:
            raise ValidationError("Block revisions are append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Block revisions are append-only")


class PlacementResolutionMode(models.TextChoices):
    LIVE = "live", "Live"
    PINNED = "pinned", "Pinned"


class PlacementAudienceProfile(models.TextChoices):
    SHARED = "shared", "Shared"
    MSP_INTERNAL = "msp_internal", "MSP internal"
    CLIENT_VISIBLE = "client_visible", "Client visible"


class DocumentPlacement(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="document_placements")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="document_placements", null=True, blank=True
    )
    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="placements")
    block = models.ForeignKey(Block, on_delete=models.PROTECT, related_name="placements")
    parent = models.ForeignKey("self", on_delete=models.PROTECT, related_name="children", null=True, blank=True)
    position = models.PositiveIntegerField()
    resolution_mode = models.CharField(
        max_length=12,
        choices=PlacementResolutionMode.choices,
        default=PlacementResolutionMode.LIVE,
    )
    audience_profile = models.CharField(
        max_length=24,
        choices=PlacementAudienceProfile.choices,
        default=PlacementAudienceProfile.SHARED,
    )
    pinned_revision = models.ForeignKey(
        BlockRevision,
        on_delete=models.PROTECT,
        related_name="pinned_placements",
        null=True,
        blank=True,
    )

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(
                fields=["document", "position"],
                condition=models.Q(parent__isnull=True),
                name="unique_document_root_position",
            ),
            models.UniqueConstraint(
                fields=["parent", "position"],
                condition=models.Q(parent__isnull=False),
                name="unique_document_child_position",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(resolution_mode=PlacementResolutionMode.LIVE, pinned_revision__isnull=True)
                    | models.Q(resolution_mode=PlacementResolutionMode.PINNED, pinned_revision__isnull=False)
                ),
                name="document_placement_resolution_target",
            ),
            models.CheckConstraint(
                condition=models.Q(audience_profile__in=PlacementAudienceProfile.values),
                name="document_placement_audience_profile",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(parent__isnull=False)
                    | ~models.Q(position=0)
                    | models.Q(audience_profile=PlacementAudienceProfile.SHARED)
                ),
                name="document_primary_placement_shared",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "organization", "document", "parent", "position"],
                name="core_docpl_scope_tree_idx",
            ),
            models.Index(
                fields=["tenant", "block", "resolution_mode"],
                name="core_docpl_block_mode_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.document_id} position {self.position}"

    def clean(self) -> None:
        if self.document_id and (
            self.document.tenant_id != self.tenant_id or self.document.organization_id != self.organization_id
        ):
            raise ValidationError("Placement must use its document workspace scope")
        if self.block_id and self.block.tenant_id != self.tenant_id:
            raise ValidationError("Placed block must belong to the placement tenant")
        parent = self.parent if self.parent_id else None
        if parent is not None and (
            parent.document_id != self.document_id
            or parent.tenant_id != self.tenant_id
            or parent.organization_id != self.organization_id
        ):
            raise ValidationError("Placement parent must belong to the same document")
        if self.parent_id is None and self.position == 0 and self.audience_profile != PlacementAudienceProfile.SHARED:
            raise ValidationError("The primary document placement must be shared")
        if parent is not None and (
            parent.audience_profile != PlacementAudienceProfile.SHARED
            and parent.audience_profile != self.audience_profile
        ):
            raise ValidationError("A child placement cannot widen its parent's audience")
        if self.resolution_mode == PlacementResolutionMode.LIVE and self.pinned_revision_id is not None:
            raise ValidationError("Live placements cannot pin a revision")
        if self.resolution_mode == PlacementResolutionMode.PINNED and self.pinned_revision_id is None:
            raise ValidationError("Pinned placements require a revision")
        pinned_revision = self.pinned_revision if self.pinned_revision_id else None
        if pinned_revision is not None and pinned_revision.block_id != self.block_id:
            raise ValidationError("Pinned revision must belong to the placed block")


class DocumentationListingReference(TimestampedModel):
    """Projects an MSP-owned document into one client documentation index."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="documentation_references")
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="documentation_references")
    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="listing_references")
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "document"],
                condition=models.Q(archived_at__isnull=True),
                name="unique_active_documentation_listing_reference",
            )
        ]
        indexes = [models.Index(fields=["tenant", "organization", "archived_at"])]

    def __str__(self) -> str:
        return f"{self.document_id} listed in {self.organization_id}"


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="audit_events", null=True, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=120)
    entity_id = models.UUIDField(null=True, blank=True)
    request_id = models.UUIDField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = models.Manager()
    scoped = TenantScopedManager()

    class Meta:
        ordering = ("-occurred_at",)
        indexes = [models.Index(fields=["tenant", "action", "occurred_at"])]

    def __str__(self) -> str:
        return f"{self.action} at {self.occurred_at}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self._state.adding is False:
            raise ValidationError("Audit events are append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Audit events are append-only")


class OutboxEventState(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    DELIVERED = "delivered", "Delivered"
    DEAD_LETTER = "dead_letter", "Dead letter"


class OutboxEvent(models.Model):
    """A durable, value-minimized domain event awaiting asynchronous delivery."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="outbox_events")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="outbox_events",
        null=True,
        blank=True,
    )
    topic = models.CharField(max_length=120)
    subject_id = models.UUIDField()
    idempotency_key = models.CharField(max_length=200)
    payload = models.JSONField(default=dict)
    state = models.CharField(max_length=20, choices=OutboxEventState.choices, default=OutboxEventState.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    available_at = models.DateTimeField(default=timezone.now)
    locked_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = TenantScopedManager()

    class Meta:
        ordering = ("created_at", "id")
        constraints = [
            models.UniqueConstraint(fields=["tenant", "idempotency_key"], name="unique_tenant_outbox_key"),
            models.CheckConstraint(condition=models.Q(attempts__lte=100), name="outbox_attempts_bounded"),
            models.CheckConstraint(
                condition=(
                    models.Q(state=OutboxEventState.DELIVERED, delivered_at__isnull=False, locked_at__isnull=True)
                    | models.Q(
                        state__in=[OutboxEventState.PENDING, OutboxEventState.DEAD_LETTER],
                        delivered_at__isnull=True,
                        locked_at__isnull=True,
                    )
                    | models.Q(
                        state=OutboxEventState.PROCESSING,
                        delivered_at__isnull=True,
                        locked_at__isnull=False,
                    )
                ),
                name="outbox_state_timestamps_consistent",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "state", "available_at", "created_at"]),
            models.Index(fields=["tenant", "topic", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.topic}:{self.subject_id}"


class OutboxDeliveryReceipt(models.Model):
    """Append-only proof that one named consumer accepted an outbox event."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="outbox_delivery_receipts")
    event = models.ForeignKey(OutboxEvent, on_delete=models.PROTECT, related_name="delivery_receipts")
    consumer = models.CharField(max_length=80)
    processed_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = TenantScopedManager()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["event", "consumer"], name="unique_outbox_consumer_receipt")]
        indexes = [models.Index(fields=["tenant", "processed_at"])]

    def __str__(self) -> str:
        return f"{self.consumer}:{self.event_id}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self._state.adding is False:
            raise ValidationError("Outbox delivery receipts are append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Outbox delivery receipts are append-only")


class WebhookDirection(models.TextChoices):
    OUTBOUND = "outbound", "Outbound"
    INBOUND = "inbound", "Inbound"


class WebhookDeliveryState(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    DELIVERED = "delivered", "Delivered"
    DEAD_LETTER = "dead_letter", "Dead letter"


class WebhookEndpoint(models.Model):
    """Exact-organization webhook configuration discovered before inbound RLS binding."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="webhook_endpoints")
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="webhook_endpoints")
    direction = models.CharField(max_length=16, choices=WebhookDirection.choices)
    name = models.CharField(max_length=100)
    url = models.URLField(max_length=500, blank=True)
    topics = models.JSONField(default=list)
    secret_envelope = models.JSONField()
    secret_prefix = models.CharField(max_length=16)
    secret_generation = models.PositiveIntegerField(default=1)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_webhook_endpoints",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = models.Manager()
    scoped = TenantScopedManager()

    class Meta:
        ordering = ("name", "id")
        indexes = [models.Index(fields=("tenant", "organization", "direction", "active"))]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(direction=WebhookDirection.OUTBOUND, url__gt="")
                    | models.Q(direction=WebhookDirection.INBOUND, url="")
                ),
                name="webhook_direction_url_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(secret_generation__gte=1), name="webhook_secret_generation_valid"
            ),
        ]

    def __str__(self) -> str:
        return f"Webhook endpoint {self.id}"

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Webhook endpoints are retained and deactivated, not deleted")


class WebhookOutboundDelivery(models.Model):
    """Value-minimized delivery lifecycle for one endpoint/event pair."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="webhook_outbound_deliveries")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="webhook_outbound_deliveries",
    )
    endpoint = models.ForeignKey(WebhookEndpoint, on_delete=models.PROTECT, related_name="outbound_deliveries")
    event = models.ForeignKey(OutboxEvent, on_delete=models.PROTECT, related_name="webhook_deliveries")
    state = models.CharField(
        max_length=20,
        choices=WebhookDeliveryState.choices,
        default=WebhookDeliveryState.PENDING,
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    available_at = models.DateTimeField(default=timezone.now)
    locked_at = models.DateTimeField(null=True, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    last_error_code = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-created_at", "id")
        constraints = [
            models.UniqueConstraint(fields=("endpoint", "event"), name="unique_webhook_endpoint_event"),
            models.CheckConstraint(condition=models.Q(attempts__lte=20), name="webhook_attempts_bounded"),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        state=WebhookDeliveryState.DELIVERED,
                        delivered_at__isnull=False,
                        locked_at__isnull=True,
                    )
                    | models.Q(
                        state__in=[WebhookDeliveryState.PENDING, WebhookDeliveryState.DEAD_LETTER],
                        delivered_at__isnull=True,
                        locked_at__isnull=True,
                    )
                    | models.Q(
                        state=WebhookDeliveryState.PROCESSING,
                        delivered_at__isnull=True,
                        locked_at__isnull=False,
                    )
                ),
                name="webhook_delivery_state_valid",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant", "state", "available_at", "created_at")),
            models.Index(fields=("tenant", "organization", "created_at")),
        ]

    def __str__(self) -> str:
        return f"Webhook delivery {self.id}"


class WebhookInboundReceipt(models.Model):
    """Append-only replay ledger that retains no inbound body or signature."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="webhook_inbound_receipts")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="webhook_inbound_receipts",
    )
    endpoint = models.ForeignKey(WebhookEndpoint, on_delete=models.PROTECT, related_name="inbound_receipts")
    delivery_id = models.CharField(max_length=100)
    event_type = models.CharField(max_length=120)
    body_sha256 = models.CharField(max_length=64)
    received_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-received_at", "id")
        constraints = [
            models.UniqueConstraint(fields=("endpoint", "delivery_id"), name="unique_inbound_webhook_delivery"),
        ]
        indexes = [models.Index(fields=("tenant", "organization", "received_at"))]

    def __str__(self) -> str:
        return f"Inbound webhook receipt {self.id}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self._state.adding is False:
            raise ValidationError("Inbound webhook receipts are append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Inbound webhook receipts are append-only")


class IntegrationProvider(models.TextChoices):
    NETBOX = "netbox", "NetBox"


class IntegrationConnection(TimestampedModel):
    """A provider connection whose credential is readable only through the worker boundary."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="integration_connections")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="integration_connections")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="integration_connections", null=True, blank=True
    )
    provider = models.CharField(max_length=32, choices=IntegrationProvider.choices)
    name = models.CharField(max_length=100)
    base_url = models.URLField(max_length=500)
    configuration = models.JSONField(default=dict, blank=True)
    secret_envelope = models.JSONField()
    secret_generation = models.PositiveIntegerField(default=1)
    active = models.BooleanField(default=True)
    sync_interval_minutes = models.PositiveIntegerField(default=60)
    next_sync_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_integration_connections"
    )

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("name", "id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(provider__in=IntegrationProvider.values), name="integration_provider_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(secret_generation__gte=1), name="integration_secret_generation_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(sync_interval_minutes__gte=5) & models.Q(sync_interval_minutes__lte=10080),
                name="integration_sync_interval_bounded",
            ),
            models.UniqueConstraint(fields=("workspace", "name"), name="integration_connection_name_unique"),
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "active"), name="core_intconn_scope_idx"),
            models.Index(fields=("tenant", "active", "next_sync_at"), name="core_intconn_due_idx"),
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        if self.workspace_id and (
            self.workspace.tenant_id != self.tenant_id or self.workspace.organization_id != self.organization_id
        ):
            raise ValidationError("Integration connection Workspace ownership does not match")
        if not isinstance(self.configuration, dict):
            raise ValidationError("Integration configuration must be an object")

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Integration connections are retained and deactivated, not deleted")


class IntegrationJobState(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    SUCCEEDED = "succeeded", "Succeeded"
    DEAD_LETTER = "dead_letter", "Dead letter"


class IntegrationSyncJob(models.Model):
    """Durable, idempotent execution record with bounded retry metadata."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="integration_sync_jobs")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="integration_sync_jobs")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="integration_sync_jobs", null=True, blank=True
    )
    connection = models.ForeignKey(IntegrationConnection, on_delete=models.PROTECT, related_name="sync_jobs")
    idempotency_key = models.CharField(max_length=160)
    trigger = models.CharField(max_length=20, default="scheduled")
    state = models.CharField(max_length=20, choices=IntegrationJobState.choices, default=IntegrationJobState.PENDING)
    cursor_before = models.CharField(max_length=500, blank=True)
    cursor_after = models.CharField(max_length=500, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    available_at = models.DateTimeField(default=timezone.now)
    locked_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=64, blank=True)
    result_counts = models.JSONField(default=dict)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="requested_integration_sync_jobs",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-created_at", "id")
        constraints = [
            models.UniqueConstraint(fields=("connection", "idempotency_key"), name="integration_job_idempotent"),
            models.CheckConstraint(condition=models.Q(attempts__lte=8), name="integration_job_attempts_bounded"),
            models.CheckConstraint(
                condition=models.Q(trigger__in=("scheduled", "manual")), name="integration_job_trigger_valid"
            ),
        ]
        indexes = [
            models.Index(fields=("tenant", "state", "available_at"), name="core_intjob_due_idx"),
            models.Index(fields=("workspace", "created_at"), name="core_intjob_scope_idx"),
        ]

    def __str__(self) -> str:
        return f"Integration job {self.id}"


class IntegrationObservation(models.Model):
    """Value-minimized immutable remote identity observation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="integration_observations")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="integration_observations")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="integration_observations", null=True, blank=True
    )
    job = models.ForeignKey(IntegrationSyncJob, on_delete=models.PROTECT, related_name="observations")
    remote_type = models.CharField(max_length=64)
    remote_id = models.CharField(max_length=160)
    fingerprint = models.CharField(max_length=64)
    observed_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("remote_type", "remote_id", "id")
        constraints = [
            models.UniqueConstraint(fields=("job", "remote_type", "remote_id"), name="integration_observation_unique"),
            models.CheckConstraint(
                condition=models.Q(fingerprint__regex=r"^[0-9a-f]{64}$"), name="integration_observation_digest_valid"
            ),
        ]
        indexes = [models.Index(fields=("workspace", "remote_type", "remote_id"), name="core_intobs_remote_idx")]

    def __str__(self) -> str:
        return f"{self.remote_type}:{self.remote_id}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ValidationError("Integration observations are append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Integration observations are append-only")


class IntegrationLogEvent(models.Model):
    """Structured allowlisted operational metadata; never provider text or response bodies."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="integration_log_events")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="integration_log_events")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="integration_log_events", null=True, blank=True
    )
    connection = models.ForeignKey(IntegrationConnection, on_delete=models.PROTECT, related_name="log_events")
    job = models.ForeignKey(
        IntegrationSyncJob, on_delete=models.PROTECT, related_name="log_events", null=True, blank=True
    )
    level = models.CharField(max_length=12)
    code = models.CharField(max_length=64)
    metrics = models.JSONField(default=dict)
    occurred_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-occurred_at", "id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(level__in=("info", "warning", "error")),
                name="integration_log_level_valid",
            )
        ]
        indexes = [models.Index(fields=("tenant", "occurred_at"), name="core_intlog_retention_idx")]

    def __str__(self) -> str:
        return f"{self.level}:{self.code}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ValidationError("Integration log events are append-only")
        return super().save(*args, **kwargs)


class IntegrationConflictStatus(models.TextChoices):
    OPEN = "open", "Open"
    KEEP_LOCAL = "keep_local", "Keep local"
    ACCEPT_REMOTE = "accept_remote", "Accept remote identity"
    IGNORED = "ignored", "Ignored"


class IntegrationConflict(TimestampedModel):
    """Reviewable difference that cannot mutate a TekDocs domain record implicitly."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="integration_conflicts")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="integration_conflicts")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="integration_conflicts", null=True, blank=True
    )
    connection = models.ForeignKey(IntegrationConnection, on_delete=models.PROTECT, related_name="conflicts")
    observation = models.ForeignKey(
        IntegrationObservation, on_delete=models.PROTECT, related_name="conflicts", null=True, blank=True
    )
    local_entity = models.ForeignKey(
        Entity, on_delete=models.PROTECT, related_name="integration_conflicts", null=True, blank=True
    )
    remote_type = models.CharField(max_length=64)
    remote_id = models.CharField(max_length=160)
    difference = models.CharField(max_length=32)
    remote_fingerprint = models.CharField(max_length=64, blank=True)
    local_fingerprint = models.CharField(max_length=64, blank=True)
    status = models.CharField(
        max_length=20, choices=IntegrationConflictStatus.choices, default=IntegrationConflictStatus.OPEN
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="resolved_integration_conflicts",
        null=True,
        blank=True,
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("status", "remote_type", "remote_id", "id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=IntegrationConflictStatus.values),
                name="integration_conflict_status_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(difference__in=("unmatched", "changed")),
                name="integration_conflict_difference_valid",
            ),
            models.CheckConstraint(
                condition=(models.Q(remote_fingerprint="") | models.Q(remote_fingerprint__regex=r"^[0-9a-f]{64}$"))
                & (models.Q(local_fingerprint="") | models.Q(local_fingerprint__regex=r"^[0-9a-f]{64}$")),
                name="integration_conflict_digests_valid",
            ),
            models.UniqueConstraint(
                fields=("connection", "remote_type", "remote_id"),
                condition=models.Q(status=IntegrationConflictStatus.OPEN),
                name="integration_open_conflict_unique",
            ),
        ]
        indexes = [models.Index(fields=("workspace", "status"), name="core_intconf_scope_idx")]

    def __str__(self) -> str:
        return f"{self.remote_type}:{self.remote_id}:{self.status}"


class ImportBatchState(models.TextChoices):
    PREVIEW_READY = "preview_ready", "Preview ready"
    APPLYING = "applying", "Applying"
    APPLIED = "applied", "Applied"
    CANCELLED = "cancelled", "Cancelled"
    FAILED = "failed", "Failed"


class ImportRowAction(models.TextChoices):
    CREATE = "create", "Create"
    UPDATE = "update", "Update"
    UNCHANGED = "unchanged", "Unchanged"
    CONFLICT = "conflict", "Conflict"
    REJECTED = "rejected", "Rejected"


class ImportBatch(models.Model):
    """Bounded import preview whose raw source bytes are never retained."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="import_batches")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="import_batches")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="import_batches", null=True, blank=True
    )
    source_format = models.CharField(max_length=32)
    schema_version = models.PositiveSmallIntegerField(default=1)
    source_filename = models.CharField(max_length=240)
    source_digest = models.CharField(max_length=64)
    state = models.CharField(max_length=20, choices=ImportBatchState.choices, default=ImportBatchState.PREVIEW_READY)
    result_counts = models.JSONField(default=dict)
    last_error_code = models.CharField(max_length=64, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_import_batches"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    applied_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-created_at", "id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(state__in=ImportBatchState.values), name="import_batch_state_valid"
            ),
            models.CheckConstraint(condition=models.Q(schema_version=1), name="import_batch_schema_v1"),
            models.CheckConstraint(
                condition=models.Q(source_digest__regex=r"^[0-9a-f]{64}$"),
                name="import_batch_digest_valid",
            ),
        ]
        indexes = [models.Index(fields=("workspace", "created_at"), name="core_importbatch_scope_idx")]

    def __str__(self) -> str:
        return f"Import batch {self.id}"


class ImportRow(models.Model):
    """Normalized, value-bounded staging row and retained value-safe result."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="import_rows")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="import_rows")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="import_rows", null=True, blank=True
    )
    batch = models.ForeignKey(ImportBatch, on_delete=models.PROTECT, related_name="rows")
    row_number = models.PositiveIntegerField()
    record_type = models.CharField(max_length=40)
    external_key = models.CharField(max_length=160)
    fingerprint = models.CharField(max_length=64)
    action = models.CharField(max_length=16, choices=ImportRowAction.choices)
    reason_code = models.CharField(max_length=64, blank=True)
    normalized_data = models.JSONField(default=dict)
    local_entity = models.ForeignKey(
        Entity, on_delete=models.PROTECT, related_name="import_rows", null=True, blank=True
    )

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("row_number", "id")
        constraints = [
            models.UniqueConstraint(fields=("batch", "row_number"), name="import_row_number_unique"),
            models.CheckConstraint(
                condition=models.Q(action__in=ImportRowAction.values), name="import_row_action_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(fingerprint__regex=r"^[0-9a-f]{64}$"), name="import_row_digest_valid"
            ),
        ]
        indexes = [models.Index(fields=("workspace", "batch", "action"), name="core_importrow_scope_idx")]

    def __str__(self) -> str:
        return f"{self.record_type}:{self.external_key}:{self.action}"


class ImportExternalKey(TimestampedModel):
    """Stable source identity mapped to one exact-Workspace TekDocs entity."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="import_external_keys")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="import_external_keys")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="import_external_keys", null=True, blank=True
    )
    source_system = models.CharField(max_length=32)
    record_type = models.CharField(max_length=40)
    external_key = models.CharField(max_length=160)
    local_entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="import_external_keys")
    last_fingerprint = models.CharField(max_length=64)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("source_system", "record_type", "external_key", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("workspace", "source_system", "record_type", "external_key"),
                name="import_external_key_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(last_fingerprint__regex=r"^[0-9a-f]{64}$"),
                name="import_external_key_digest_valid",
            ),
        ]
        indexes = [models.Index(fields=("workspace", "source_system", "record_type"), name="core_importkey_scope_idx")]

    def __str__(self) -> str:
        return f"{self.source_system}:{self.record_type}:{self.external_key}"


def git_export_upload_to(instance: "GitExportBundle", _filename: str) -> str:
    return str(PurePosixPath("git-exports") / str(instance.tenant_id) / str(instance.id))


class GitExportBundle(models.Model):
    """Retained deterministic, sanitized archive suitable for a Git working tree."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="git_export_bundles")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="git_export_bundles")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="git_export_bundles", null=True, blank=True
    )
    selection_manifest = models.JSONField()
    content_digest = models.CharField(max_length=64)
    artifact = models.FileField(upload_to=git_export_upload_to, max_length=500)
    byte_size = models.PositiveBigIntegerField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="git_export_bundles"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-created_at", "id")
        indexes = [models.Index(fields=("workspace", "created_at"), name="core_gitexport_scope_idx")]

    def __str__(self) -> str:
        return f"Git export {self.id}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ValidationError("Git export bundles are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Git export bundles are retained")


class NotificationSurface(models.TextChoices):
    MSP = "msp", "MSP"
    CLIENT_PORTAL = "client_portal", "Client portal"


class InboxNotification(models.Model):
    """A durable recipient edge whose display projection is authorized at read time."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="inbox_notifications")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="inbox_notifications",
    )
    event = models.ForeignKey(OutboxEvent, on_delete=models.PROTECT, related_name="inbox_notifications")
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="inbox_notifications",
    )
    surface = models.CharField(max_length=20, choices=NotificationSurface.choices)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = TenantScopedManager()

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("event", "recipient", "surface"),
                name="unique_event_recipient_surface",
            ),
            models.CheckConstraint(
                condition=models.Q(surface__in=NotificationSurface.values),
                name="inbox_notification_surface_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=("tenant", "recipient", "surface", "read_at", "created_at"),
                name="core_inbox_recipient_idx",
            )
        ]

    def __str__(self) -> str:
        return f"{self.recipient_id}:{self.event_id}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self._state.adding is False:
            persisted = InboxNotification.objects.only("read_at").get(pk=self.pk)
            if any(
                getattr(self, field) != getattr(persisted, field)
                for field in ("tenant_id", "organization_id", "event_id", "recipient_id", "surface", "created_at")
            ):
                raise ValidationError("Inbox notification identity is immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Inbox notifications cannot be deleted")


class NotificationPreference(models.Model):
    """Per-surface email choices; security and invitation-token mail is outside this boundary."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="notification_preferences")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="notification_preferences",
    )
    surface = models.CharField(max_length=20, choices=NotificationSurface.choices)
    email_enabled = models.BooleanField(default=True)
    invitation_events = models.BooleanField(default=True)
    publication_events = models.BooleanField(default=True)
    delivery_mode = models.CharField(
        max_length=16,
        choices=(("immediate", "Immediate"), ("hourly", "Hourly digest"), ("daily", "Daily digest")),
        default="immediate",
    )
    timezone = models.CharField(max_length=64, default="UTC")
    quiet_start = models.TimeField(null=True, blank=True)
    quiet_end = models.TimeField(null=True, blank=True)
    daily_digest_hour = models.PositiveSmallIntegerField(default=8)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = models.Manager()
    scoped = TenantScopedManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("tenant", "user", "surface"),
                name="unique_notification_preference_surface",
            ),
            models.CheckConstraint(
                condition=models.Q(surface__in=NotificationSurface.values),
                name="notification_preference_surface_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(delivery_mode__in=("immediate", "hourly", "daily")),
                name="notification_preference_delivery_mode_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(daily_digest_hour__lte=23),
                name="notification_preference_daily_hour_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(quiet_start__isnull=True, quiet_end__isnull=True)
                    | (
                        models.Q(quiet_start__isnull=False, quiet_end__isnull=False)
                        & ~models.Q(quiet_start=models.F("quiet_end"))
                    )
                ),
                name="notification_preference_quiet_window_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.surface}"

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Notification preferences cannot be deleted")


class NotificationEmailState(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    DELIVERED = "delivered", "Delivered"
    SUPPRESSED = "suppressed", "Suppressed"
    DEAD_LETTER = "dead_letter", "Dead letter"


class NotificationEmailDelivery(models.Model):
    """A value-minimized SMTP work item linked to one authorized inbox edge."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="notification_email_deliveries")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="notification_email_deliveries",
    )
    notification = models.OneToOneField(
        InboxNotification,
        on_delete=models.PROTECT,
        related_name="email_delivery",
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="notification_email_deliveries",
    )
    surface = models.CharField(max_length=20, choices=NotificationSurface.choices)
    state = models.CharField(
        max_length=20,
        choices=NotificationEmailState.choices,
        default=NotificationEmailState.PENDING,
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    available_at = models.DateTimeField(default=timezone.now)
    locked_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=64, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    retry_generation = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = TenantScopedManager()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(attempts__lte=100), name="notification_email_attempts_bounded"),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        state=NotificationEmailState.DELIVERED,
                        delivered_at__isnull=False,
                        locked_at__isnull=True,
                    )
                    | models.Q(
                        state__in=[
                            NotificationEmailState.PENDING,
                            NotificationEmailState.SUPPRESSED,
                            NotificationEmailState.DEAD_LETTER,
                        ],
                        delivered_at__isnull=True,
                        locked_at__isnull=True,
                    )
                    | models.Q(
                        state=NotificationEmailState.PROCESSING,
                        delivered_at__isnull=True,
                        locked_at__isnull=False,
                    )
                ),
                name="notification_email_state_timestamps_consistent",
            ),
        ]
        indexes = [
            models.Index(
                fields=("tenant", "state", "available_at", "created_at"),
                name="core_notice_email_due_idx",
            ),
            models.Index(
                fields=("tenant", "recipient", "surface", "created_at"),
                name="core_notice_email_user_idx",
            ),
        ]

    def __str__(self) -> str:
        return str(self.id)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Notification email deliveries cannot be deleted")


class ComplianceFramework(TimestampedModel):
    """Stable identity for one Workspace-owned compliance framework."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="compliance_frameworks")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="compliance_frameworks")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="compliance_frameworks",
        null=True,
        blank=True,
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="compliance_framework_record")
    current_revision = models.ForeignKey(
        "ComplianceCatalogRevision",
        on_delete=models.PROTECT,
        related_name="current_for_frameworks",
        null=True,
        blank=True,
    )

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("entity__display_name", "id")
        indexes = [models.Index(fields=("workspace", "created_at"), name="core_compfw_scope_idx")]

    def __str__(self) -> str:
        return self.entity.display_name


class ComplianceCatalogRevision(models.Model):
    """Immutable metadata and ordered-control snapshot for one framework version."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="compliance_catalog_revisions")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="compliance_catalog_revisions")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="compliance_catalog_revisions",
        null=True,
        blank=True,
    )
    framework = models.ForeignKey(ComplianceFramework, on_delete=models.PROTECT, related_name="revisions")
    revision_number = models.PositiveIntegerField()
    version_label = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    source_url = models.URLField(max_length=500, blank=True)
    content_digest = models.CharField(max_length=64)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_compliance_catalog_revisions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-revision_number", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("framework", "revision_number"),
                name="compliance_catalog_revision_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(revision_number__gte=1),
                name="compliance_catalog_revision_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(content_digest__regex=r"^[0-9a-f]{64}$"),
                name="compliance_catalog_digest_valid",
            ),
        ]
        indexes = [models.Index(fields=("workspace", "created_at"), name="core_compcat_scope_idx")]

    def __str__(self) -> str:
        return f"{self.framework} revision {self.revision_number}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ValidationError("Compliance catalog revisions are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Compliance catalog revisions are retained")


class ComplianceControl(models.Model):
    """Stable addressable identity for a control across catalog revisions."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="compliance_controls")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="compliance_controls")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="compliance_controls",
        null=True,
        blank=True,
    )
    framework = models.ForeignKey(ComplianceFramework, on_delete=models.PROTECT, related_name="controls")
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="compliance_control_record")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("created_at", "id")
        indexes = [models.Index(fields=("workspace", "framework"), name="core_compctl_scope_idx")]

    def __str__(self) -> str:
        return self.entity.display_name


class ComplianceControlRevision(models.Model):
    """Immutable Markdown-capable control content reused by catalog snapshots."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="compliance_control_revisions")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="compliance_control_revisions")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="compliance_control_revisions",
        null=True,
        blank=True,
    )
    control = models.ForeignKey(ComplianceControl, on_delete=models.PROTECT, related_name="revisions")
    revision_number = models.PositiveIntegerField()
    identifier = models.CharField(max_length=100)
    title = models.CharField(max_length=240)
    description = models.TextField(blank=True)
    guidance = models.TextField(blank=True)
    content_digest = models.CharField(max_length=64)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_compliance_control_revisions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-revision_number", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("control", "revision_number"),
                name="compliance_control_revision_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(revision_number__gte=1),
                name="compliance_control_revision_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(content_digest__regex=r"^[0-9a-f]{64}$"),
                name="compliance_control_digest_valid",
            ),
        ]
        indexes = [models.Index(fields=("workspace", "created_at"), name="core_compctlrev_scope_idx")]

    def __str__(self) -> str:
        return f"{self.identifier} revision {self.revision_number}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ValidationError("Compliance control revisions are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Compliance control revisions are retained")


class ComplianceCatalogEntry(models.Model):
    """One immutable ordered control-revision membership in a catalog snapshot."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="compliance_catalog_entries")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="compliance_catalog_entries")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="compliance_catalog_entries",
        null=True,
        blank=True,
    )
    catalog_revision = models.ForeignKey(
        ComplianceCatalogRevision,
        on_delete=models.PROTECT,
        related_name="entries",
    )
    control_revision = models.ForeignKey(
        ComplianceControlRevision,
        on_delete=models.PROTECT,
        related_name="catalog_entries",
    )
    position = models.PositiveIntegerField()

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("catalog_revision", "position"),
                name="compliance_catalog_entry_position_unique",
            ),
            models.UniqueConstraint(
                fields=("catalog_revision", "control_revision"),
                name="compliance_catalog_entry_revision_unique",
            ),
        ]
        indexes = [models.Index(fields=("workspace", "catalog_revision"), name="core_compentry_scope_idx")]

    def __str__(self) -> str:
        return f"{self.catalog_revision}: {self.control_revision}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ValidationError("Compliance catalog entries are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Compliance catalog entries are retained")


class ComplianceApplicability(models.TextChoices):
    UNASSESSED = "unassessed", "Not evaluated"
    APPLICABLE = "applicable", "Applicable"
    NOT_APPLICABLE = "not_applicable", "Not applicable"


class ComplianceImplementationStatus(models.TextChoices):
    NOT_STARTED = "not_started", "Not started"
    PLANNED = "planned", "Planned"
    IN_PROGRESS = "in_progress", "In progress"
    IMPLEMENTED = "implemented", "Implemented"
    NOT_IMPLEMENTED = "not_implemented", "Not implemented"


class ComplianceControlAssignment(TimestampedModel):
    """Current exact-Workspace applicability and ownership state for one stable control."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="compliance_assignments")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="compliance_assignments")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="compliance_assignments", null=True, blank=True
    )
    framework = models.ForeignKey(ComplianceFramework, on_delete=models.PROTECT, related_name="assignments")
    control = models.ForeignKey(ComplianceControl, on_delete=models.PROTECT, related_name="assignments")
    control_revision = models.ForeignKey(
        ComplianceControlRevision, on_delete=models.PROTECT, related_name="assignments"
    )
    applicability = models.CharField(
        max_length=20, choices=ComplianceApplicability.choices, default=ComplianceApplicability.UNASSESSED
    )
    implementation_status = models.CharField(
        max_length=24,
        choices=ComplianceImplementationStatus.choices,
        default=ComplianceImplementationStatus.NOT_STARTED,
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_compliance_assignments",
        null=True,
        blank=True,
    )
    review_due_date = models.DateField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("framework_id", "control_id")
        constraints = [models.UniqueConstraint(fields=("workspace", "control"), name="compliance_assignment_unique")]
        indexes = [models.Index(fields=("workspace", "implementation_status"), name="core_compassign_scope_idx")]

    def __str__(self) -> str:
        return f"{self.control} assignment"


class ComplianceAssignmentReview(models.Model):
    """Append-only review decision and exact assignment-state snapshot."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="compliance_assignment_reviews")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="compliance_assignment_reviews")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="compliance_assignment_reviews", null=True, blank=True
    )
    assignment = models.ForeignKey(ComplianceControlAssignment, on_delete=models.PROTECT, related_name="reviews")
    control_revision = models.ForeignKey(
        ComplianceControlRevision, on_delete=models.PROTECT, related_name="assignment_reviews"
    )
    applicability = models.CharField(max_length=20, choices=ComplianceApplicability.choices)
    implementation_status = models.CharField(max_length=24, choices=ComplianceImplementationStatus.choices)
    decision = models.CharField(max_length=120)
    note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="compliance_assignment_reviews"
    )
    reviewed_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-reviewed_at", "id")
        indexes = [models.Index(fields=("workspace", "reviewed_at"), name="core_compreview_scope_idx")]

    def __str__(self) -> str:
        return f"Review of {self.assignment} at {self.reviewed_at}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ValidationError("Compliance assignment reviews are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Compliance assignment reviews are retained")


class ComplianceEvidenceKind(models.TextChoices):
    NOTE = "note", "Recorded note"
    URL = "url", "External URL"
    ENTITY = "entity", "TekDocs entity"


class ComplianceEvidenceStatus(models.TextChoices):
    COLLECTED = "collected", "Collected"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"
    EXPIRED = "expired", "Expired"


class ComplianceEvidence(TimestampedModel):
    """Reusable exact-Workspace evidence identity with a bounded collection window."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="compliance_evidence")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="compliance_evidence")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="compliance_evidence", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="compliance_evidence")
    kind = models.CharField(max_length=16, choices=ComplianceEvidenceKind.choices)
    source_url = models.URLField(max_length=500, blank=True)
    source_entity = models.ForeignKey(
        Entity, on_delete=models.PROTECT, related_name="compliance_evidence_sources", null=True, blank=True
    )
    summary = models.TextField(blank=True)
    collection_start = models.DateField(null=True, blank=True)
    collection_end = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_compliance_evidence"
    )

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("entity__display_name", "id")
        indexes = [models.Index(fields=("workspace", "kind"), name="core_compevidence_scope_idx")]

    def __str__(self) -> str:
        return self.entity.display_name


class ComplianceEvidenceLink(models.Model):
    """Retained control-assignment edge to reusable evidence and an exact control revision."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="compliance_evidence_links")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="compliance_evidence_links")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="compliance_evidence_links", null=True, blank=True
    )
    assignment = models.ForeignKey(ComplianceControlAssignment, on_delete=models.PROTECT, related_name="evidence_links")
    evidence = models.ForeignKey(ComplianceEvidence, on_delete=models.PROTECT, related_name="control_links")
    control_revision = models.ForeignKey(
        ComplianceControlRevision, on_delete=models.PROTECT, related_name="evidence_links"
    )
    linked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="linked_compliance_evidence"
    )
    linked_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("linked_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("assignment", "evidence", "control_revision"),
                name="compliance_evidence_link_unique",
            )
        ]
        indexes = [models.Index(fields=("workspace", "linked_at"), name="core_compevlink_scope_idx")]

    def __str__(self) -> str:
        return f"{self.evidence} linked to {self.assignment}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ValidationError("Compliance evidence links are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Compliance evidence links are retained")


class ComplianceEvidenceReview(models.Model):
    """Append-only evidence review decision history."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="compliance_evidence_reviews")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="compliance_evidence_reviews")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="compliance_evidence_reviews", null=True, blank=True
    )
    evidence = models.ForeignKey(ComplianceEvidence, on_delete=models.PROTECT, related_name="reviews")
    status = models.CharField(max_length=16, choices=ComplianceEvidenceStatus.choices)
    decision = models.CharField(max_length=120)
    note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="compliance_evidence_reviews"
    )
    reviewed_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-reviewed_at", "id")
        indexes = [models.Index(fields=("workspace", "reviewed_at"), name="core_compevreview_scope_idx")]

    def __str__(self) -> str:
        return f"{self.status} review of {self.evidence}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ValidationError("Compliance evidence reviews are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Compliance evidence reviews are retained")


class ComplianceRiskStatus(models.TextChoices):
    OPEN = "open", "Open"
    MONITORING = "monitoring", "Monitoring"
    ACCEPTED = "accepted", "Accepted"
    CLOSED = "closed", "Closed"


class ComplianceRiskTreatment(models.TextChoices):
    MITIGATE = "mitigate", "Mitigate"
    AVOID = "avoid", "Avoid"
    TRANSFER = "transfer", "Transfer"
    ACCEPT = "accept", "Accept"


class ComplianceRisk(TimestampedModel):
    """Current exact-Workspace risk projection; decisions are retained as events."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="compliance_risks")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="compliance_risks")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="compliance_risks", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="compliance_risk")
    assignment = models.ForeignKey(
        ComplianceControlAssignment, on_delete=models.PROTECT, related_name="risks", null=True, blank=True
    )
    description = models.TextField(blank=True)
    likelihood = models.PositiveSmallIntegerField()
    impact = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=16, choices=ComplianceRiskStatus.choices)
    treatment = models.CharField(max_length=16, choices=ComplianceRiskTreatment.choices)
    treatment_plan = models.TextField(blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="owned_compliance_risks", null=True, blank=True
    )
    due_date = models.DateField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="accepted_compliance_risks",
        null=True,
        blank=True,
    )
    accepted_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-updated_at", "entity__display_name", "id")
        indexes = [models.Index(fields=("workspace", "status", "due_date"), name="core_comprisk_scope_idx")]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(likelihood__gte=1, likelihood__lte=5), name="risk_likelihood_1_5"
            ),
            models.CheckConstraint(condition=models.Q(impact__gte=1, impact__lte=5), name="risk_impact_1_5"),
        ]

    def __str__(self) -> str:
        return self.entity.display_name

    @property
    def score(self) -> int:
        return self.likelihood * self.impact

    @property
    def reporting_band(self) -> str:
        if self.score >= 16:
            return "critical"
        if self.score >= 10:
            return "high"
        if self.score >= 5:
            return "moderate"
        return "low"


class ComplianceRiskEvent(models.Model):
    """Append-only risk decision and complete reporting snapshot."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="compliance_risk_events")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="compliance_risk_events")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="compliance_risk_events", null=True, blank=True
    )
    risk = models.ForeignKey(ComplianceRisk, on_delete=models.PROTECT, related_name="events")
    control_revision = models.ForeignKey(
        ComplianceControlRevision, on_delete=models.PROTECT, related_name="risk_events", null=True, blank=True
    )
    likelihood = models.PositiveSmallIntegerField()
    impact = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=16, choices=ComplianceRiskStatus.choices)
    treatment = models.CharField(max_length=16, choices=ComplianceRiskTreatment.choices)
    treatment_plan = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    decision = models.CharField(max_length=120)
    note = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="compliance_risk_events"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-recorded_at", "id")
        indexes = [models.Index(fields=("workspace", "recorded_at"), name="core_compriskev_scope_idx")]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(likelihood__gte=1, likelihood__lte=5), name="risk_event_likelihood_1_5"
            ),
            models.CheckConstraint(condition=models.Q(impact__gte=1, impact__lte=5), name="risk_event_impact_1_5"),
        ]

    def __str__(self) -> str:
        return f"{self.risk} decision at {self.recorded_at}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ValidationError("Compliance risk events are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Compliance risk events are retained")


class ComplianceEvidenceBundle(models.Model):
    """Immutable signed point-in-time compliance evidence package."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="compliance_evidence_bundles")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="compliance_evidence_bundles")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="compliance_evidence_bundles", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="compliance_evidence_bundle")
    reason = models.CharField(max_length=500)
    audience = models.CharField(max_length=32)
    manifest = models.JSONField()
    content_digest = models.CharField(max_length=64)
    signature = models.TextField()
    signature_algorithm = models.CharField(max_length=20, default="Ed25519")
    public_key = models.TextField()
    key_fingerprint = models.CharField(max_length=64)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_compliance_evidence_bundles"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-created_at", "id")
        indexes = [models.Index(fields=("workspace", "created_at"), name="core_compbundle_scope_idx")]

    def __str__(self) -> str:
        return self.entity.display_name

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ValidationError("Compliance evidence bundles are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Compliance evidence bundles are retained")


class ReminderDomain(models.TextChoices):
    COMPLIANCE = "compliance", "Compliance"
    INVENTORY = "inventory", "Inventory"
    DOMAIN = "domain", "Domain"
    DOCUMENTATION = "documentation", "Documentation"


class ReminderRecurrence(models.TextChoices):
    NONE = "none", "Does not repeat"
    ANNUAL = "annual", "Annual"


class ReminderSchedule(TimestampedModel):
    """One exact-Workspace schedule shared by deadline-producing domains."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="reminder_schedules")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="reminder_schedules")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="reminder_schedules", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="reminder_schedule")
    source_entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="reminder_schedules")
    domain = models.CharField(max_length=20, choices=ReminderDomain.choices)
    kind = models.CharField(max_length=48)
    title = models.CharField(max_length=240)
    due_on = models.DateField()
    lead_days = models.PositiveSmallIntegerField(default=30)
    recurrence = models.CharField(max_length=16, choices=ReminderRecurrence.choices, default=ReminderRecurrence.NONE)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_reminder_schedules",
        null=True,
        blank=True,
    )
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_reminder_schedules"
    )

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("due_on", "title", "id")
        indexes = [models.Index(fields=("workspace", "active", "due_on"), name="core_reminder_due_idx")]
        constraints = [
            models.CheckConstraint(condition=models.Q(lead_days__lte=3650), name="reminder_lead_days_bounded"),
            models.UniqueConstraint(
                fields=("workspace", "source_entity", "kind", "due_on"), name="reminder_source_kind_due_unique"
            ),
        ]

    def __str__(self) -> str:
        return self.title


class DomainRenewalMode(models.TextChoices):
    MANUAL = "manual", "Manual"
    AUTO = "auto", "Automatic"
    EXTERNAL = "external", "Managed externally"


class RegisteredDomainStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    PENDING = "pending", "Pending"
    EXPIRED = "expired", "Expired"
    TRANSFERRED = "transferred", "Transferred"


class DomainReviewState(models.TextChoices):
    UNREVIEWED = "unreviewed", "Unreviewed"
    CURRENT = "current", "Current"
    STALE = "stale", "Stale"
    CONFLICT = "conflict", "Conflicting source"


class DomainMonitorState(models.TextChoices):
    NEVER = "never", "Never checked"
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    CURRENT = "current", "Current"
    FAILED = "failed", "Check failed"


class DomainMonitorRunState(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"


class DomainMonitorAlertKind(models.TextChoices):
    EXPIRATION_DUE = "expiration_due", "Expiration due"
    EXPIRATION_CHANGED = "expiration_changed", "Expiration changed"
    DNS_CHANGED = "dns_changed", "DNS changed"
    COLLECTION_FAILED = "collection_failed", "Collection failed"


class CertificateEndpointProtocol(models.TextChoices):
    HTTPS = "https", "HTTPS"
    SMTPS = "smtps", "SMTP over TLS"
    IMAPS = "imaps", "IMAP over TLS"
    POP3S = "pop3s", "POP3 over TLS"


class CertificateMonitorAlertKind(models.TextChoices):
    EXPIRATION_DUE = "expiration_due", "Certificate expiration due"
    CERTIFICATE_CHANGED = "certificate_changed", "Certificate changed"
    VALIDATION_FAILED = "validation_failed", "Certificate validation failed"
    COLLECTION_FAILED = "collection_failed", "Certificate collection failed"


class RegisteredDomain(TimestampedModel):
    """Workspace-owned entered registration record; observations remain separate."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="registered_domains")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="registered_domains")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="registered_domains", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="registered_domain")
    ascii_name = models.CharField(max_length=253)
    registrar = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="registrar_domains", null=True, blank=True
    )
    registration_date = models.DateField(null=True, blank=True)
    expiration_date = models.DateField(null=True, blank=True)
    renewal_mode = models.CharField(max_length=16, choices=DomainRenewalMode.choices)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_registered_domains",
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=16, choices=RegisteredDomainStatus.choices)
    notes = models.TextField(blank=True)
    review_state = models.CharField(
        max_length=16, choices=DomainReviewState.choices, default=DomainReviewState.UNREVIEWED
    )
    observed_expiration_date = models.DateField(null=True, blank=True)
    last_reviewed_at = models.DateTimeField(null=True, blank=True)
    monitoring_enabled = models.BooleanField(default=True)
    monitor_interval_hours = models.PositiveSmallIntegerField(default=24)
    next_monitor_at = models.DateTimeField(default=timezone.now)
    last_monitor_at = models.DateTimeField(null=True, blank=True)
    monitor_state = models.CharField(
        max_length=16, choices=DomainMonitorState.choices, default=DomainMonitorState.NEVER
    )
    monitor_error_code = models.CharField(max_length=64, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_registered_domains"
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("ascii_name", "id")
        indexes = [models.Index(fields=("workspace", "status", "expiration_date"), name="core_domain_scope_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=("workspace", "ascii_name"),
                condition=models.Q(archived_at__isnull=True),
                name="registered_domain_active_name_unique",
            )
        ]

    def __str__(self) -> str:
        return self.ascii_name


class DomainReviewEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="domain_review_events")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="domain_review_events")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="domain_review_events", null=True, blank=True
    )
    domain = models.ForeignKey(RegisteredDomain, on_delete=models.PROTECT, related_name="review_events")
    state = models.CharField(max_length=16, choices=DomainReviewState.choices)
    entered_expiration_date = models.DateField(null=True, blank=True)
    observed_expiration_date = models.DateField(null=True, blank=True)
    source = models.CharField(max_length=120)
    note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="domain_review_events", null=True, blank=True
    )
    reviewed_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-reviewed_at", "id")

    def __str__(self) -> str:
        return f"{self.state}:{self.domain_id}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ValidationError("Domain review events are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Domain review events are retained")


class HostnameProvenance(models.TextChoices):
    ENTERED = "entered", "Entered"
    DISCOVERED = "discovered", "Discovered"


class ManagedHostname(TimestampedModel):
    """A managed hostname below one registered-domain apex."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="managed_hostnames")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="managed_hostnames")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="managed_hostnames", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="managed_hostname")
    domain = models.ForeignKey(RegisteredDomain, on_delete=models.PROTECT, related_name="hostnames")
    parent = models.ForeignKey("self", on_delete=models.PROTECT, related_name="children", null=True, blank=True)
    ascii_name = models.CharField(max_length=253)
    provenance = models.CharField(max_length=16, choices=HostnameProvenance.choices)
    source = models.CharField(max_length=120, blank=True)
    observed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_managed_hostnames"
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("ascii_name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("workspace", "ascii_name"),
                condition=models.Q(archived_at__isnull=True),
                name="managed_hostname_active_name_unique",
            )
        ]

    def __str__(self) -> str:
        return self.ascii_name


class DomainDNSObservation(models.Model):
    """Append-only normalized DNS answer observed for a managed hostname."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="domain_dns_observations")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="domain_dns_observations")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="domain_dns_observations", null=True, blank=True
    )
    domain = models.ForeignKey(RegisteredDomain, on_delete=models.PROTECT, related_name="dns_observations")
    hostname = models.ForeignKey(
        ManagedHostname, on_delete=models.PROTECT, related_name="dns_observations", null=True, blank=True
    )
    record_type = models.CharField(max_length=16)
    value = models.CharField(max_length=1_024)
    ttl = models.PositiveIntegerField(null=True, blank=True)
    provenance = models.CharField(max_length=16, choices=HostnameProvenance.choices)
    source = models.CharField(max_length=120)
    content_digest = models.CharField(max_length=64)
    observed_at = models.DateTimeField()
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="recorded_domain_dns_observations",
        null=True,
        blank=True,
    )

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-observed_at", "id")
        indexes = [models.Index(fields=("workspace", "hostname", "observed_at"), name="core_domain_dns_obs_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=("domain", "hostname", "record_type", "content_digest", "observed_at"),
                name="domain_dns_observation_unique",
                nulls_distinct=False,
            )
        ]

    def __str__(self) -> str:
        return f"{self.record_type}:{self.domain_id}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ValidationError("DNS observations are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("DNS observations are retained")


class DomainMonitorRun(models.Model):
    """Bounded asynchronous RDAP and DNS collection lifecycle for one domain."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="domain_monitor_runs")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="domain_monitor_runs")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="domain_monitor_runs", null=True, blank=True
    )
    domain = models.ForeignKey(RegisteredDomain, on_delete=models.PROTECT, related_name="monitoring_runs")
    trigger = models.CharField(max_length=16, choices=(("manual", "Manual"), ("scheduled", "Scheduled")))
    state = models.CharField(
        max_length=16, choices=DomainMonitorRunState.choices, default=DomainMonitorRunState.PENDING
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="requested_domain_monitor_runs",
        null=True,
        blank=True,
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    available_at = models.DateTimeField(default=timezone.now)
    locked_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    rdap_source = models.CharField(max_length=120, blank=True)
    rdap_digest = models.CharField(max_length=64, blank=True)
    observed_expiration_date = models.DateField(null=True, blank=True)
    observed_registrar = models.CharField(max_length=240, blank=True)
    dns_source = models.CharField(max_length=120, blank=True)
    dns_digest = models.CharField(max_length=64, blank=True)
    dnssec_validated = models.BooleanField(null=True, blank=True)
    dns_record_count = models.PositiveSmallIntegerField(default=0)
    caa_digest = models.CharField(max_length=64, blank=True)
    caa_record_count = models.PositiveSmallIntegerField(default=0)
    evidence_digest = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-created_at", "id")
        indexes = [
            models.Index(fields=("workspace", "state", "available_at"), name="core_domainrun_due_idx"),
            models.Index(fields=("domain", "created_at"), name="core_domainrun_history_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(attempts__lte=5), name="domain_monitor_attempts_bounded"),
            models.CheckConstraint(
                condition=models.Q(trigger__in=("manual", "scheduled")), name="domain_monitor_trigger_valid"
            ),
            models.CheckConstraint(
                condition=~models.Q(state=DomainMonitorRunState.SUCCEEDED) | ~models.Q(evidence_digest=""),
                name="domain_monitor_success_has_digest",
            ),
        ]

    def __str__(self) -> str:
        return f"Domain monitor run {self.id}"

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Domain monitoring runs are retained")


class DomainMonitorAlert(models.Model):
    """Append-only, value-minimized in-app notification produced by monitoring."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="domain_monitor_alerts")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="domain_monitor_alerts")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="domain_monitor_alerts", null=True, blank=True
    )
    domain = models.ForeignKey(RegisteredDomain, on_delete=models.PROTECT, related_name="monitoring_alerts")
    run = models.ForeignKey(DomainMonitorRun, on_delete=models.PROTECT, related_name="alerts")
    kind = models.CharField(max_length=32, choices=DomainMonitorAlertKind.choices)
    observed_expiration_date = models.DateField(null=True, blank=True)
    prior_expiration_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-created_at", "id")
        constraints = [models.UniqueConstraint(fields=("run", "kind"), name="domain_monitor_alert_run_kind_unique")]

    def __str__(self) -> str:
        return f"{self.kind}:{self.domain_id}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ValidationError("Domain monitoring alerts are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Domain monitoring alerts are retained")


class CertificateEndpoint(TimestampedModel):
    """One direct-TLS service endpoint related to a registered domain or managed hostname."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="certificate_endpoints")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="certificate_endpoints")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="certificate_endpoints", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="certificate_endpoint")
    domain = models.ForeignKey(RegisteredDomain, on_delete=models.PROTECT, related_name="certificate_endpoints")
    hostname = models.ForeignKey(
        ManagedHostname, on_delete=models.PROTECT, related_name="certificate_endpoints", null=True, blank=True
    )
    protocol = models.CharField(max_length=16, choices=CertificateEndpointProtocol.choices)
    port = models.PositiveSmallIntegerField()
    monitoring_enabled = models.BooleanField(default=True)
    monitor_interval_hours = models.PositiveSmallIntegerField(default=24)
    next_monitor_at = models.DateTimeField(default=timezone.now)
    last_monitor_at = models.DateTimeField(null=True, blank=True)
    monitor_state = models.CharField(
        max_length=16, choices=DomainMonitorState.choices, default=DomainMonitorState.NEVER
    )
    monitor_error_code = models.CharField(max_length=64, blank=True)
    current_leaf_sha256 = models.CharField(max_length=64, blank=True)
    current_not_after = models.DateTimeField(null=True, blank=True)
    current_hostname_valid = models.BooleanField(null=True, blank=True)
    current_trust_valid = models.BooleanField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_certificate_endpoints"
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("domain__ascii_name", "hostname__ascii_name", "protocol", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("workspace", "domain", "protocol"),
                condition=models.Q(archived_at__isnull=True, hostname__isnull=True),
                name="certificate_apex_endpoint_active_unique",
            ),
            models.UniqueConstraint(
                fields=("workspace", "hostname", "protocol"),
                condition=models.Q(archived_at__isnull=True, hostname__isnull=False),
                name="certificate_host_endpoint_active_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(protocol__in=CertificateEndpointProtocol.values),
                name="certificate_endpoint_protocol_valid",
            ),
        ]
        indexes = [
            models.Index(fields=("workspace", "monitor_state", "next_monitor_at"), name="core_certendpoint_due_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.protocol}://{self.target_name}:{self.port}"

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Certificate endpoints must be archived")

    @property
    def target_name(self) -> str:
        if self.hostname_id and self.hostname is not None:
            return self.hostname.ascii_name
        return self.domain.ascii_name


class CertificateMonitorRun(models.Model):
    """Retained, bounded certificate and validation evidence for one endpoint scan."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="certificate_monitor_runs")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="certificate_monitor_runs")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="certificate_monitor_runs", null=True, blank=True
    )
    endpoint = models.ForeignKey(CertificateEndpoint, on_delete=models.PROTECT, related_name="monitoring_runs")
    trigger = models.CharField(max_length=16, choices=(("manual", "Manual"), ("scheduled", "Scheduled")))
    state = models.CharField(
        max_length=16, choices=DomainMonitorRunState.choices, default=DomainMonitorRunState.PENDING
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="requested_certificate_monitor_runs",
        null=True,
        blank=True,
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    available_at = models.DateTimeField(default=timezone.now)
    locked_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    leaf_sha256 = models.CharField(max_length=64, blank=True)
    chain_sha256 = models.CharField(max_length=64, blank=True)
    chain_length = models.PositiveSmallIntegerField(default=0)
    subject_common_name = models.CharField(max_length=253, blank=True)
    issuer_common_name = models.CharField(max_length=253, blank=True)
    serial_sha256 = models.CharField(max_length=64, blank=True)
    san_sha256 = models.CharField(max_length=64, blank=True)
    san_count = models.PositiveSmallIntegerField(default=0)
    not_before = models.DateTimeField(null=True, blank=True)
    not_after = models.DateTimeField(null=True, blank=True)
    hostname_valid = models.BooleanField(null=True, blank=True)
    trust_valid = models.BooleanField(null=True, blank=True)
    tls_version = models.CharField(max_length=32, blank=True)
    cipher_name = models.CharField(max_length=64, blank=True)
    evidence_digest = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-created_at", "id")
        constraints = [
            models.CheckConstraint(condition=models.Q(attempts__lte=5), name="certificate_run_attempts_bounded"),
            models.CheckConstraint(
                condition=models.Q(trigger__in=("manual", "scheduled")), name="certificate_run_trigger_valid"
            ),
            models.CheckConstraint(
                condition=~models.Q(state=DomainMonitorRunState.SUCCEEDED) | ~models.Q(evidence_digest=""),
                name="certificate_run_success_has_digest",
            ),
        ]
        indexes = [
            models.Index(fields=("workspace", "state", "available_at"), name="core_certrun_due_idx"),
            models.Index(fields=("endpoint", "created_at"), name="core_certrun_history_idx"),
        ]

    def __str__(self) -> str:
        return f"Certificate monitor run {self.id}"

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Certificate monitoring runs are retained")


class CertificateMonitorAlert(models.Model):
    """Append-only value-minimized certificate monitoring alert."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="certificate_monitor_alerts")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="certificate_monitor_alerts")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="certificate_monitor_alerts", null=True, blank=True
    )
    endpoint = models.ForeignKey(CertificateEndpoint, on_delete=models.PROTECT, related_name="monitoring_alerts")
    run = models.ForeignKey(CertificateMonitorRun, on_delete=models.PROTECT, related_name="alerts")
    kind = models.CharField(max_length=32, choices=CertificateMonitorAlertKind.choices)
    observed_not_after = models.DateTimeField(null=True, blank=True)
    prior_not_after = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-created_at", "id")
        constraints = [models.UniqueConstraint(fields=("run", "kind"), name="certificate_alert_run_kind_unique")]

    def __str__(self) -> str:
        return f"{self.kind}:{self.endpoint_id}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ValidationError("Certificate monitoring alerts are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Certificate monitoring alerts are retained")


class RelationshipGraphFamily(models.TextChoices):
    NETWORK = "network", "Network"
    ASSET = "asset", "Asset"
    DOCUMENT = "document", "Document"


class RelationshipGraphView(TimestampedModel):
    """A named, workspace-owned graph query and its optional manual positions."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="relationship_graph_views")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="relationship_graph_views")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="relationship_graph_views", null=True, blank=True
    )
    name = models.CharField(max_length=120)
    family = models.CharField(max_length=16, choices=RelationshipGraphFamily.choices)
    root_entity = models.ForeignKey(
        Entity, on_delete=models.PROTECT, related_name="relationship_graph_views", null=True, blank=True
    )
    depth = models.PositiveSmallIntegerField(default=2)
    edge_limit = models.PositiveSmallIntegerField(default=100)
    positions = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_relationship_graph_views"
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("name", "id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(family__in=RelationshipGraphFamily.values), name="graph_view_family_valid"
            ),
            models.CheckConstraint(condition=models.Q(depth__gte=1, depth__lte=3), name="graph_view_depth_bounded"),
            models.CheckConstraint(
                condition=models.Q(edge_limit__gte=1, edge_limit__lte=200), name="graph_view_limit_bounded"
            ),
            models.UniqueConstraint(
                fields=("workspace", "name"),
                condition=models.Q(archived_at__isnull=True),
                name="graph_view_workspace_name_unique",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Relationship graph views must be archived")


class RelationshipGraphSnapshot(models.Model):
    """An immutable, exact authorized graph retained for review and export."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="relationship_graph_snapshots")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="relationship_graph_snapshots")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="relationship_graph_snapshots", null=True, blank=True
    )
    view = models.ForeignKey(RelationshipGraphView, on_delete=models.PROTECT, related_name="snapshots")
    graph = models.JSONField()
    content_digest = models.CharField(max_length=64)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_relationship_graph_snapshots"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-created_at", "id")
        indexes = [models.Index(fields=("view", "created_at"), name="core_graphsnapshot_idx")]

    def __str__(self) -> str:
        return f"{self.view}: {self.created_at}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ValidationError("Relationship graph snapshots are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Relationship graph snapshots are retained")


class DocumentKeyBinding(TimestampedModel):
    """A named binding from a document to the record its key expressions resolve against.

    A document declares bindings such as ``subject``; a key of ``subject.gateway``
    then reads that field from this target. Binding to ``Entity`` rather than to a
    narrower record type is deliberate: every domain record is entity-anchored, so
    one target type gives one authorization path rather than one per domain.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="document_key_bindings")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="document_key_bindings")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="document_key_bindings", null=True, blank=True
    )
    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="key_bindings")
    name = models.CharField(max_length=40)
    target_entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="document_key_bindings")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_document_key_bindings"
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("name", "id")
        constraints = [
            # One spelling per binding name, using the key grammar itself rather than a
            # copy of it. The stored key expression is permanent, so a name that cannot
            # appear in a key must never reach the table.
            models.CheckConstraint(
                condition=models.Q(name__regex=BINDING_NAME_PATTERN),
                name="document_key_binding_name_valid",
            ),
            # Uniqueness applies to live bindings only, so a name can be re-declared
            # against a different record after the previous binding is retired.
            models.UniqueConstraint(
                fields=("document", "name"),
                condition=models.Q(archived_at__isnull=True),
                name="document_key_binding_name_unique",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        # Retained rather than removed: a retired binding is the record of what a
        # document's keys used to resolve against, which is the first question asked
        # when a document's values change meaning.
        raise ValidationError("Document key bindings must be archived")


class DataFlowEndpointKind(models.TextChoices):
    INTERNAL = "internal", "Internal record"
    EXTERNAL = "external", "External party"


class DataFlowDirection(models.TextChoices):
    ONE_WAY = "one_way", "One way"
    BIDIRECTIONAL = "bidirectional", "Bidirectional"


class DataFlowTransfer(models.TextChoices):
    API = "api", "API"
    FILE_TRANSFER = "file_transfer", "File transfer"
    DATABASE_REPLICATION = "database_replication", "Database replication"
    MESSAGE_QUEUE = "message_queue", "Message queue"
    EMAIL = "email", "Email"
    PHYSICAL_MEDIA = "physical_media", "Physical media"
    MANUAL_ENTRY = "manual_entry", "Manual entry"
    BACKUP = "backup", "Backup"
    OTHER = "other", "Other"


class DataFlowClassification(models.TextChoices):
    PUBLIC = "public", "Public"
    INTERNAL = "internal", "Internal"
    CONFIDENTIAL = "confidential", "Confidential"
    RESTRICTED = "restricted", "Restricted"
    PERSONAL_DATA = "personal_data", "Personal data"
    SPECIAL_CATEGORY = "special_category", "Special category personal data"


class DataFlowProtection(models.TextChoices):
    NONE = "none", "No protection recorded"
    IN_TRANSIT = "in_transit", "Encrypted in transit"
    AT_REST = "at_rest", "Encrypted at rest"
    IN_TRANSIT_AND_AT_REST = "in_transit_and_at_rest", "Encrypted in transit and at rest"
    UNKNOWN = "unknown", "Unknown"


class DataFlowProvenance(models.TextChoices):
    """How much weight a reader may place on a flow record.

    ADR 0088 requires views to distinguish recorded fact from imported observation and
    unverified draft, because a plausible diagram is otherwise mistaken for evidence.
    """

    RECORDED_FACT = "recorded_fact", "Recorded fact"
    IMPORTED_OBSERVATION = "imported_observation", "Imported observation"
    UNVERIFIED_DRAFT = "unverified_draft", "Unverified draft"


class DataFlow(TimestampedModel):
    """Stable addressable identity for one Workspace-owned data flow."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="data_flows")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="data_flows")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="data_flows",
        null=True,
        blank=True,
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="data_flow_record")
    current_revision = models.ForeignKey(
        "DataFlowRevision",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_data_flows",
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("entity__display_name", "id")
        indexes = [models.Index(fields=("workspace", "archived_at"), name="core_dataflow_scope_idx")]

    def __str__(self) -> str:
        return self.entity.display_name

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id
            or self.entity.organization_id != self.organization_id
            or self.entity.entity_type != "data_flow"
        ):
            raise ValidationError("Data flow entity identity and scope must match")


class DataFlowRevision(models.Model):
    """One immutable statement of what a flow carried, between whom, and how.

    Every field a reader would rely on lives here rather than on `DataFlow`, so a
    changed classification or protection posture produces a new revision instead of
    silently rewriting what earlier evidence asserted.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="data_flow_revisions")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="data_flow_revisions")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="data_flow_revisions",
        null=True,
        blank=True,
    )
    data_flow = models.ForeignKey(DataFlow, on_delete=models.PROTECT, related_name="revisions")
    revision_number = models.PositiveIntegerField()
    source_kind = models.CharField(max_length=16, choices=DataFlowEndpointKind.choices)
    source_entity = models.ForeignKey(
        Entity, on_delete=models.PROTECT, related_name="data_flow_sources", null=True, blank=True
    )
    source_label = models.CharField(max_length=240, blank=True)
    destination_kind = models.CharField(max_length=16, choices=DataFlowEndpointKind.choices)
    destination_entity = models.ForeignKey(
        Entity, on_delete=models.PROTECT, related_name="data_flow_destinations", null=True, blank=True
    )
    destination_label = models.CharField(max_length=240, blank=True)
    direction = models.CharField(max_length=16, choices=DataFlowDirection.choices)
    transfer_mechanism = models.CharField(max_length=32, choices=DataFlowTransfer.choices)
    data_classification = models.CharField(max_length=24, choices=DataFlowClassification.choices)
    purpose = models.CharField(max_length=1000)
    crosses_trust_boundary = models.BooleanField()
    protection = models.CharField(max_length=32, choices=DataFlowProtection.choices)
    owner_entity = models.ForeignKey(
        Entity, on_delete=models.PROTECT, related_name="owned_data_flows", null=True, blank=True
    )
    review_due_on = models.DateField(null=True, blank=True)
    provenance = models.CharField(max_length=24, choices=DataFlowProvenance.choices)
    content_digest = models.CharField(max_length=64)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_data_flow_revisions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-revision_number", "id")
        constraints = [
            models.UniqueConstraint(fields=("data_flow", "revision_number"), name="data_flow_revision_unique"),
            models.CheckConstraint(condition=models.Q(revision_number__gte=1), name="data_flow_revision_positive"),
            models.CheckConstraint(
                condition=models.Q(content_digest__regex=r"^[0-9a-f]{64}$"), name="data_flow_revision_digest_valid"
            ),
            # An endpoint is either a record in this Workspace or a named outside party.
            # Permitting both would let a label contradict the record it sits beside.
            models.CheckConstraint(
                condition=(
                    models.Q(source_kind="internal", source_entity__isnull=False, source_label="")
                    | (models.Q(source_kind="external", source_entity__isnull=True) & ~models.Q(source_label=""))
                ),
                name="data_flow_revision_source_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(destination_kind="internal", destination_entity__isnull=False, destination_label="")
                    | (
                        models.Q(destination_kind="external", destination_entity__isnull=True)
                        & ~models.Q(destination_label="")
                    )
                ),
                name="data_flow_revision_destination_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(direction__in=DataFlowDirection.values), name="data_flow_revision_direction_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(transfer_mechanism__in=DataFlowTransfer.values),
                name="data_flow_revision_transfer_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(data_classification__in=DataFlowClassification.values),
                name="data_flow_revision_classification_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(protection__in=DataFlowProtection.values),
                name="data_flow_revision_protection_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(provenance__in=DataFlowProvenance.values),
                name="data_flow_revision_provenance_valid",
            ),
        ]
        indexes = [models.Index(fields=("workspace", "created_at"), name="core_dataflowrev_scope_idx")]

    def __str__(self) -> str:
        return f"{self.data_flow_id} revision {self.revision_number}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ValidationError("Data flow revisions are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Data flow revisions are retained")


class DataFlowSnapshot(models.Model):
    """An immutable capture of the flows in force at one moment.

    The payload holds each flow's exact revision identifier and asserted values rather
    than a reference to its flow, so a later revision cannot change what a retained
    snapshot said. This is the same guarantee `DocumentPublication` gives a document.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="data_flow_snapshots")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="data_flow_snapshots")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="data_flow_snapshots", null=True, blank=True
    )
    title = models.CharField(max_length=240)
    reason = models.CharField(max_length=1000, blank=True)
    flows = models.JSONField()
    flow_count = models.PositiveIntegerField()
    content_digest = models.CharField(max_length=64)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_data_flow_snapshots"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-created_at", "id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(content_digest__regex=r"^[0-9a-f]{64}$"), name="data_flow_snapshot_digest_valid"
            ),
        ]
        indexes = [models.Index(fields=("workspace", "created_at"), name="core_dataflowsnap_idx")]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ValidationError("Data flow snapshots are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Data flow snapshots are retained")
