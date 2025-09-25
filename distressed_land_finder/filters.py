from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional

from .sources.base import PropertyListing


@dataclass(slots=True)
class FilterCriteria:
    max_price: Optional[float] = None
    min_acreage: Optional[float] = None
    counties: Optional[List[str]] = None
    sale_types: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    include_pending: bool = False
    keywords: Optional[List[str]] = None


def apply_filters(listings: Iterable[PropertyListing], criteria: FilterCriteria) -> List[PropertyListing]:
    def matches(listing: PropertyListing) -> bool:
        if criteria.max_price is not None and listing.minimum_bid is not None:
            if listing.minimum_bid > criteria.max_price:
                return False
        if criteria.min_acreage is not None and listing.acreage is not None:
            if listing.acreage < criteria.min_acreage:
                return False
        if criteria.counties:
            normalized = {c.strip().lower() for c in criteria.counties if c}
            if normalized and (listing.county or "").lower() not in normalized:
                return False
        if criteria.sale_types:
            normalized_sale_types = {s.lower() for s in criteria.sale_types}
            sale_type = (listing.sale_type or "").lower()
            if normalized_sale_types and sale_type not in normalized_sale_types:
                return False
        if not criteria.include_pending:
            status = (listing.status or "").lower()
            if status in {"cancelled", "canceled", "sold", "redeemed"}:
                return False
        if criteria.tags:
            normalized_tags = {tag.lower() for tag in criteria.tags}
            listing_tags = {tag.lower() for tag in listing.tags}
            if not normalized_tags.intersection(listing_tags):
                return False
        if criteria.keywords:
            haystack = " ".join(
                part.lower()
                for part in [
                    listing.title,
                    listing.description,
                    listing.address,
                    listing.city,
                    listing.county,
                ]
                if part
            )
            for keyword in criteria.keywords:
                if keyword.lower() not in haystack:
                    return False
        return True

    return [listing for listing in listings if matches(listing)]


@dataclass(slots=True)
class ScoreResult:
    listing: PropertyListing
    score: float
    reasons: List[str]


def score_listings(listings: Iterable[PropertyListing], *, reference_date: Optional[datetime] = None) -> List[ScoreResult]:
    ref = reference_date or datetime.utcnow()
    results: List[ScoreResult] = []
    for listing in listings:
        score = 0.0
        reasons: List[str] = []

        if listing.minimum_bid is not None and listing.minimum_bid >= 0:
            # Reward lower bids; clamp around $300k.
            normalized = max(0.0, min(1.0, (300_000 - listing.minimum_bid) / 300_000))
            bid_points = normalized * 45
            if bid_points:
                reasons.append(f"Lower minimum bid bonus (+{bid_points:.1f})")
            score += bid_points
        else:
            reasons.append("Unknown minimum bid")

        if listing.acreage is not None and listing.acreage > 0:
            acreage_points = min(listing.acreage, 20) / 20 * 25
            reasons.append(f"Acreage weight (+{acreage_points:.1f})")
            score += acreage_points

        if listing.sale_date:
            delta = (listing.sale_date - ref).days
            if delta >= 0:
                urgency_points = max(0.0, min(1.0, (60 - delta) / 60)) * 15
                if urgency_points:
                    reasons.append(f"Upcoming sale urgency (+{urgency_points:.1f})")
                score += urgency_points
            else:
                reasons.append("Sale date in the past")
        else:
            reasons.append("Unknown sale date")

        if listing.property_type:
            lowered = listing.property_type.lower()
            if "commercial" in lowered:
                score += 8
                reasons.append("Commercial designation (+8.0)")
            if any(keyword in lowered for keyword in ["land", "lot", "acre"]):
                score += 6
                reasons.append("Vacant land keyword (+6.0)")

        if listing.sale_type:
            lowered = listing.sale_type.lower()
            if "tax" in lowered or "deed" in lowered or "lien" in lowered:
                score += 4
                reasons.append("Tax delinquency sale (+4.0)")
            if "seiz" in lowered or "federal" in lowered:
                score += 4
                reasons.append("Seizure sale (+4.0)")

        if listing.tags:
            tag_bonus = min(len(listing.tags), 5)
            if tag_bonus:
                score += tag_bonus
                reasons.append(f"Source tags (+{tag_bonus:.1f})")

        results.append(ScoreResult(listing=listing, score=score, reasons=reasons))

    results.sort(key=lambda item: item.score, reverse=True)
    return results
