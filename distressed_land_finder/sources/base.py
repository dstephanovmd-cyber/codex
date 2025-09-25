from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Protocol


@dataclass(slots=True)
class PropertyListing:
    """Normalized representation of a distressed property listing."""

    source: str
    external_id: str
    title: str
    url: str
    state: str
    county: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    zip_code: Optional[str] = None
    sale_date: Optional[datetime] = None
    sale_type: Optional[str] = None
    status: Optional[str] = None
    minimum_bid: Optional[float] = None
    current_bid: Optional[float] = None
    deposit: Optional[float] = None
    acreage: Optional[float] = None
    property_type: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    description: Optional[str] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert the listing to a serializable dictionary."""

        data: Dict[str, Any] = {
            "source": self.source,
            "external_id": self.external_id,
            "title": self.title,
            "url": self.url,
            "state": self.state,
            "county": self.county,
            "city": self.city,
            "address": self.address,
            "zip_code": self.zip_code,
            "sale_date": self.sale_date.isoformat() if self.sale_date else None,
            "sale_type": self.sale_type,
            "status": self.status,
            "minimum_bid": self.minimum_bid,
            "current_bid": self.current_bid,
            "deposit": self.deposit,
            "acreage": self.acreage,
            "property_type": self.property_type,
            "tags": self.tags,
            "description": self.description,
            "raw_data": self.raw_data,
        }
        return data

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "PropertyListing":
        sale_date_raw = payload.get("sale_date")
        sale_date = None
        if sale_date_raw:
            try:
                sale_date = datetime.fromisoformat(sale_date_raw)
            except ValueError:
                sale_date = None
        return cls(
            source=payload["source"],
            external_id=payload["external_id"],
            title=payload["title"],
            url=payload["url"],
            state=payload.get("state", ""),
            county=payload.get("county"),
            city=payload.get("city"),
            address=payload.get("address"),
            zip_code=payload.get("zip_code"),
            sale_date=sale_date,
            sale_type=payload.get("sale_type"),
            status=payload.get("status"),
            minimum_bid=payload.get("minimum_bid"),
            current_bid=payload.get("current_bid"),
            deposit=payload.get("deposit"),
            acreage=payload.get("acreage"),
            property_type=payload.get("property_type"),
            tags=list(payload.get("tags", [])),
            description=payload.get("description"),
            raw_data=dict(payload.get("raw_data", {})),
        )


class AuctionSource(Protocol):
    slug: str
    title: str

    def fetch_listings(self) -> Iterable[PropertyListing]:
        ...


def merge_tags(*tag_groups: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    merged: List[str] = []
    for group in tag_groups:
        for tag in group:
            normalized = tag.strip().lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                merged.append(tag)
    return merged
