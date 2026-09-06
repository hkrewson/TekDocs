from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import AuditEvent, Organization, StockItem, StockMovement, StockMovementType, Tenant


class StockError(ValueError):
    pass


def _validate(record) -> None:  # type: ignore[no-untyped-def]
    try:
        record.full_clean()
    except ValidationError as exc:
        if hasattr(exc, "message_dict"):
            detail = " ".join(message for messages in exc.message_dict.values() for message in messages)
        else:
            detail = " ".join(exc.messages)
        raise StockError(detail) from exc


@transaction.atomic
def create_stock_item(
    *, tenant: Tenant, actor_id: UUID, values: dict[str, object], initial_quantity: Decimal
) -> StockItem:
    record = StockItem(tenant=tenant, quantity_on_hand=Decimal("0"), **values)
    _validate(record)
    record.save()
    if initial_quantity < 0:
        raise StockError("Initial quantity cannot be negative")
    if initial_quantity:
        change_stock(
            item=record,
            actor_id=actor_id,
            movement_type=StockMovementType.RECEIVED,
            quantity_change=initial_quantity,
            client=None,
            note="Initial stock",
        )
    AuditEvent.objects.create(tenant=tenant, actor_id=actor_id, action="stock.item_created", metadata={})
    return (
        StockItem.objects.select_related("vendor")
        .prefetch_related("movements__actor", "movements__client")
        .get(pk=record.pk)
    )


@transaction.atomic
def update_stock_item(*, item: StockItem, actor_id: UUID, values: dict[str, object]) -> StockItem:
    locked = StockItem.objects.select_for_update().get(pk=item.pk)
    for field, value in values.items():
        setattr(locked, field, value)
    _validate(locked)
    locked.save(update_fields=(*values.keys(), "updated_at"))
    AuditEvent.objects.create(tenant=locked.tenant, actor_id=actor_id, action="stock.item_updated", metadata={})
    return locked


@transaction.atomic
def archive_stock_item(*, item: StockItem, actor_id: UUID) -> None:
    locked = StockItem.objects.select_for_update().get(pk=item.pk)
    if locked.archived_at is not None:
        return
    if locked.invoice_lines.filter(invoice__state="draft", stock_quantity_consumed__gt=0).exists():
        raise StockError("Remove this item from its invoice drafts before archiving it")
    from django.utils import timezone

    locked.archived_at = timezone.now()
    locked.save(update_fields=("archived_at", "updated_at"))
    AuditEvent.objects.create(tenant=locked.tenant, actor_id=actor_id, action="stock.item_archived", metadata={})


@transaction.atomic
def change_stock(
    *,
    item: StockItem,
    actor_id: UUID,
    movement_type: str,
    quantity_change: Decimal,
    client: Organization | None,
    note: str,
    occurred_at: datetime | None = None,
) -> StockMovement:
    from django.utils import timezone

    locked = StockItem.objects.select_for_update().get(pk=item.pk)
    if locked.archived_at is not None:
        raise StockError("Archived stock cannot be adjusted")
    after = locked.quantity_on_hand + quantity_change
    if after < 0:
        raise StockError(f"Only {locked.quantity_on_hand} {locked.unit} are on hand")
    movement = StockMovement(
        tenant=locked.tenant,
        stock_item=locked,
        client=client,
        movement_type=movement_type,
        quantity_change=quantity_change,
        quantity_after=after,
        note=note.strip(),
        occurred_at=occurred_at or timezone.now(),
        actor_id=actor_id,
    )
    _validate(movement)
    movement.save()  # type: ignore[no-untyped-call]
    locked.quantity_on_hand = after
    locked.save(update_fields=("quantity_on_hand", "updated_at"))
    AuditEvent.objects.create(tenant=locked.tenant, actor_id=actor_id, action="stock.quantity_changed", metadata={})
    return movement
