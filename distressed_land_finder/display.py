from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

from .filters import ScoreResult

try:
    from rich.console import Console
    from rich.table import Table
    from rich.text import Text
except ImportError:  # pragma: no cover - runtime fallback
    Console = None  # type: ignore
    Table = None  # type: ignore
    Text = None  # type: ignore


def _format_currency(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"$ {value:,.0f}"


def _format_date(value: Optional[datetime]) -> str:
    if value is None:
        return "—"
    return value.strftime("%Y-%m-%d")


def render(results: Iterable[ScoreResult], *, limit: int = 20) -> None:
    results_list = list(results)[:limit]
    if not results_list:
        print("No listings found that match your criteria.")
        return

    if Console and Table:
        console = Console()
        table = Table(title=f"Top {len(results_list)} Florida distressed land opportunities")
        table.add_column("#", justify="right")
        table.add_column("Score", justify="right")
        table.add_column("Title", overflow="fold")
        table.add_column("County")
        table.add_column("Sale Date")
        table.add_column("Min Bid")
        table.add_column("Acreage", justify="right")
        table.add_column("Source")
        for idx, result in enumerate(results_list, start=1):
            listing = result.listing
            acreage = f"{listing.acreage:.2f}" if listing.acreage is not None else "—"
            score_text = f"{result.score:.1f}"
            title_text = Text(listing.title)
            if "seiz" in (listing.sale_type or "").lower():
                title_text.stylize("bold yellow")
            if any(tag.lower() == "irs" for tag in listing.tags):
                title_text.stylize("underline")
            table.add_row(
                str(idx),
                score_text,
                title_text,
                listing.county or listing.city or "—",
                _format_date(listing.sale_date),
                _format_currency(listing.minimum_bid),
                acreage,
                listing.source,
            )
        console.print(table)
    else:
        print(f"Top {len(results_list)} Florida distressed land opportunities:")
        print("# | Score | Sale Date | Min Bid | Acres | County | Title")
        print("-" * 96)
        for idx, result in enumerate(results_list, start=1):
            listing = result.listing
            score = f"{result.score:5.1f}"
            sale_date = _format_date(listing.sale_date)
            min_bid = _format_currency(listing.minimum_bid)
            acreage = f"{listing.acreage:.2f}" if listing.acreage is not None else "—"
            county = (listing.county or listing.city or "—")[:14]
            title = listing.title[:60]
            print(f"{idx:>2} | {score} | {sale_date:>10} | {min_bid:>10} | {acreage:>5} | {county:<14} | {title}")

    print("\nTip: run with --interactive to deep-dive into individual listings.")


def describe_listing(result: ScoreResult) -> str:
    listing = result.listing
    parts = [
        f"Title       : {listing.title}",
        f"Source      : {listing.source}",
        f"External ID : {listing.external_id}",
        f"URL         : {listing.url}",
        f"Sale Type   : {listing.sale_type or '—'}",
        f"Sale Date   : {_format_date(listing.sale_date)}",
        f"Location    : {listing.address or '—'}, {listing.city or '—'}, {listing.county or '—'}, {listing.state}",
        f"Zip Code    : {listing.zip_code or '—'}",
        f"Minimum Bid : {_format_currency(listing.minimum_bid)}",
        f"Current Bid : {_format_currency(listing.current_bid)}",
        f"Deposit Req.: {_format_currency(listing.deposit)}",
        f"Acreage     : {listing.acreage if listing.acreage is not None else '—'}",
        f"Property Type: {listing.property_type or '—'}",
        f"Status      : {listing.status or '—'}",
        f"Tags        : {', '.join(listing.tags) if listing.tags else '—'}",
        f"Score       : {result.score:.1f}",
        "Score Notes :" + ("\n  - " + "\n  - ".join(result.reasons) if result.reasons else " —"),
        "Description :",
        f"  {(listing.description or 'No description provided.').strip()}",
    ]
    return "\n".join(parts)
