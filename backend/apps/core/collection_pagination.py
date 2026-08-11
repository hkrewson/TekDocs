from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

from django.db.models import Model, QuerySet
from rest_framework import serializers

Record = TypeVar("Record", bound=Model)


class BoundedCollectionQuerySerializer(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, max_value=100_000, required=False, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=100, required=False, default=50)


@dataclass(frozen=True)
class CollectionPage(Generic[Record]):
    records: list[Record]
    page: int
    page_size: int
    count: int
    has_more: bool


def paginate(records: QuerySet[Record], *, page: int, page_size: int) -> CollectionPage[Record]:
    count = records.count()
    offset = (page - 1) * page_size
    selected = list(records[offset : offset + page_size])
    return CollectionPage(
        records=selected,
        page=page,
        page_size=page_size,
        count=count,
        has_more=offset + len(selected) < count,
    )
