from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Dict, Iterable, List

from .cache import CacheManager
from .display import describe_listing, render
from .filters import FilterCriteria, apply_filters, score_listings
from .sources.base import PropertyListing

MISSING_CONNECTORS: Dict[str, str] = {}

try:  # pragma: no cover - depends on optional dependency
    from .sources.bid4assets import Bid4AssetsFloridaSource
except ModuleNotFoundError as exc:  # pragma: no cover
    Bid4AssetsFloridaSource = None  # type: ignore
    MISSING_CONNECTORS["bid4assets"] = (
        "Bid4Assets connector requires BeautifulSoup (pip install beautifulsoup4)."
    )

try:  # pragma: no cover - depends on optional dependency
    from .sources.irs import IRSRealEstateSource
except ModuleNotFoundError as exc:  # pragma: no cover
    IRSRealEstateSource = None  # type: ignore
    MISSING_CONNECTORS["irs"] = "IRS connector requires BeautifulSoup (pip install beautifulsoup4)."

SOURCES_REGISTRY = {
    slug: source
    for slug, source in {
        (getattr(IRSRealEstateSource, "slug", "irs")): IRSRealEstateSource,
        (getattr(Bid4AssetsFloridaSource, "slug", "bid4assets")): Bid4AssetsFloridaSource,
    }.items()
    if source is not None
}


def _load_demo_listings() -> List[PropertyListing]:
    demo_path = Path(__file__).resolve().parent / "demo_data" / "demo_listings.json"
    if not demo_path.exists():
        raise FileNotFoundError("Demo data file missing; reinstall the package or fetch real data.")
    payload = json.loads(demo_path.read_text())
    listings = [PropertyListing.from_dict(item) for item in payload]
    return listings


def _load_cached_listings(cache: CacheManager, source_key: str) -> List[PropertyListing]:
    cached = cache.get(source_key)
    if not cached:
        return []
    try:
        return [PropertyListing.from_dict(item) for item in cached]
    except Exception:
        return []


def _store_cache(cache: CacheManager, source_key: str, listings: Iterable[PropertyListing], ttl: int) -> None:
    payload = [listing.to_dict() for listing in listings]
    cache.set(source_key, payload, ttl=ttl)


def fetch_all_sources(selected_sources: Iterable[str], *, cache: CacheManager, ttl: int, use_cache: bool) -> List[PropertyListing]:
    listings: List[PropertyListing] = []
    for slug in selected_sources:
        source_cls = SOURCES_REGISTRY.get(slug)
        if not source_cls:
            message = MISSING_CONNECTORS.get(slug)
            if message:
                logging.warning("%s", message)
            else:
                logging.warning("Unknown source '%s'", slug)
            continue
        cache_key = f"source::{slug}"
        if use_cache:
            cached_listings = _load_cached_listings(cache, cache_key)
            if cached_listings:
                logging.info("Loaded %d cached listings from %s", len(cached_listings), slug)
                listings.extend(cached_listings)
                continue
        source = source_cls()
        fresh_listings = list(source.fetch_listings())
        logging.info("Fetched %d listings from %s", len(fresh_listings), source.title)
        if fresh_listings:
            listings.extend(fresh_listings)
            _store_cache(cache, cache_key, fresh_listings, ttl)
    cache.save()
    return listings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Discover Florida distressed land opportunities from IRS seizures and county tax deed auctions.",
    )
    parser.add_argument("--max-price", type=float, help="Maximum minimum-bid amount to include.")
    parser.add_argument("--min-acreage", type=float, help="Minimum acreage to include.")
    parser.add_argument(
        "--counties",
        type=lambda value: [item.strip() for item in value.split(",") if item.strip()],
        help="Comma-separated list of Florida counties to include.",
    )
    parser.add_argument(
        "--sale-types",
        type=lambda value: [item.strip() for item in value.split(",") if item.strip()],
        help="Only include sale types that match any of the provided values.",
    )
    parser.add_argument(
        "--tags",
        type=lambda value: [item.strip() for item in value.split(",") if item.strip()],
        help="Require at least one of these tags (e.g. IRS, Tax Deed).",
    )
    parser.add_argument(
        "--keywords",
        type=lambda value: [item.strip() for item in value.split(",") if item.strip()],
        help="Require keywords to appear in the title/location/description.",
    )
    parser.add_argument(
        "--sources",
        default="irs,bid4assets",
        help="Comma-separated list of sources to query (irs,bid4assets).",
    )
    parser.add_argument("--limit", type=int, default=20, help="Number of listings to display (default: 20).")
    parser.add_argument("--skip-cache", action="store_true", help="Ignore cache and refresh all sources.")
    parser.add_argument(
        "--cache-ttl",
        type=int,
        default=60 * 60,
        help="Cache lifetime in seconds (default: 3600).",
    )
    parser.add_argument(
        "--cache-path",
        type=Path,
        default=Path.home() / ".distressed_land_cache.json",
        help="Path for cached listings.",
    )
    parser.add_argument("--export", type=Path, help="Export filtered listings to a CSV file.")
    parser.add_argument("--interactive", action="store_true", help="Enable interactive detail viewer.")
    parser.add_argument("--demo", action="store_true", help="Use bundled demo data instead of fetching live data.")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging output.")
    return parser.parse_args()


def export_to_csv(listings: Iterable[PropertyListing], destination: Path) -> None:
    import csv

    fieldnames = [
        "source",
        "external_id",
        "title",
        "url",
        "state",
        "county",
        "city",
        "address",
        "zip_code",
        "sale_date",
        "sale_type",
        "status",
        "minimum_bid",
        "current_bid",
        "deposit",
        "acreage",
        "property_type",
        "tags",
    ]
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for listing in listings:
            row = listing.to_dict()
            row["tags"] = ", ".join(listing.tags)
            row["sale_date"] = listing.sale_date.isoformat() if listing.sale_date else ""
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def interactive_loop(scored: List[tuple[int, float, PropertyListing, object]]) -> None:
    index_lookup: Dict[int, PropertyListing] = {idx: listing for idx, _, listing, _ in scored}
    print("Enter a listing number to view details, 'r' to refresh filters, or 'q' to quit.")
    while True:
        selection = input("Command> ").strip().lower()
        if selection in {"q", "quit", "exit"}:
            break
        if selection in {"r", "refresh"}:
            print("Interactive refresh not implemented. Rerun the script with different filters.")
            continue
        if selection.isdigit():
            idx = int(selection)
            listing = index_lookup.get(idx)
            if not listing:
                print(f"Listing {idx} not in the current results.")
                continue
            scored_entry = next(item for item in scored if item[0] == idx)
            detail = describe_listing(scored_entry[3])
            print("\n" + detail + "\n")
        else:
            print("Unknown command. Enter listing number, 'r', or 'q'.")


def _build_scored_mapping(score_results):
    scored: List[tuple[int, float, PropertyListing, object]] = []
    for idx, result in enumerate(score_results, start=1):
        scored.append((idx, result.score, result.listing, result))
    return scored


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s: %(message)s")

    selected_sources = [slug.strip() for slug in args.sources.split(",") if slug.strip()]
    available_sources = set(SOURCES_REGISTRY.keys())
    missing_selected = [slug for slug in selected_sources if slug not in available_sources]
    if missing_selected:
        for slug in missing_selected:
            message = MISSING_CONNECTORS.get(slug) or f"Unknown source '{slug}'"
            logging.warning(message)
        selected_sources = [slug for slug in selected_sources if slug in available_sources]
    if not selected_sources and not args.demo:
        print("No data sources are available. Install optional dependencies such as beautifulsoup4 or use --demo.")
        return
    cache = CacheManager(args.cache_path)

    if args.demo:
        listings = _load_demo_listings()
    else:
        listings = fetch_all_sources(selected_sources, cache=cache, ttl=args.cache_ttl, use_cache=not args.skip_cache)

    criteria = FilterCriteria(
        max_price=args.max_price,
        min_acreage=args.min_acreage,
        counties=args.counties,
        sale_types=args.sale_types,
        tags=args.tags,
        keywords=args.keywords,
    )
    filtered = apply_filters(listings, criteria)
    score_results = score_listings(filtered)

    render(score_results, limit=args.limit)

    if args.export:
        export_to_csv((result.listing for result in score_results), args.export)
        print(f"Exported {len(score_results)} listings to {args.export}")

    if args.interactive:
        scored_mapping = _build_scored_mapping(score_results)
        interactive_loop(scored_mapping)


if __name__ == "__main__":  # pragma: no cover
    main()
