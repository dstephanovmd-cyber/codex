from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from ..http import HttpClient
from .base import PropertyListing, merge_tags


@dataclass
class _RawBid4AssetsListing:
    identifier: str
    title: str
    url: str
    minimum_bid: Optional[float]
    current_bid: Optional[float]
    city: Optional[str]
    county: Optional[str]
    state: str
    sale_date: Optional[datetime]
    sale_type: Optional[str]
    acreage: Optional[float]
    property_type: Optional[str]
    status: Optional[str]
    description: Optional[str]


class Bid4AssetsFloridaSource:
    slug = "bid4assets"
    title = "Bid4Assets Florida County Auctions"

    BASE_URL = "https://www.bid4assets.com/"
    SEARCH_PATH = "mvc/listing"

    def __init__(self, *, client: Optional[HttpClient] = None) -> None:
        self.client = client or HttpClient()
        self.log = logging.getLogger(self.__class__.__name__)

    def fetch_listings(self) -> Iterable[PropertyListing]:
        html = self._fetch_listing_page()
        raw_listings = self._parse_raw_listings(html)
        listings: List[PropertyListing] = []
        for raw in raw_listings:
            tags = ["Bid4Assets", "Tax Deed"]
            if raw.property_type and "commercial" in raw.property_type.lower():
                tags.append("Commercial")
            if raw.sale_type and "lien" in raw.sale_type.lower():
                tags.append("Tax Lien")
            listing = PropertyListing(
                source=self.title,
                external_id=raw.identifier,
                title=raw.title,
                url=raw.url,
                state=raw.state,
                county=raw.county,
                city=raw.city,
                sale_date=raw.sale_date,
                sale_type=raw.sale_type or "County tax deed auction",
                status=raw.status or "Active",
                minimum_bid=raw.minimum_bid,
                current_bid=raw.current_bid,
                acreage=raw.acreage,
                property_type=raw.property_type,
                description=raw.description,
                tags=merge_tags(tags),
                raw_data={"source": "bid4assets"},
            )
            listings.append(listing)
        return listings

    def _fetch_listing_page(self) -> str:
        params = {
            "state": "FL",
            "upcoming": "true",
            "category": "Real Estate",
            "type": "upcoming",
        }
        try:
            response = self.client.get(urljoin(self.BASE_URL, self.SEARCH_PATH), params=params)
        except Exception as exc:  # pragma: no cover - network failure
            self.log.warning("Unable to fetch Bid4Assets listings: %s", exc)
            return ""
        return response.text

    def _parse_raw_listings(self, html: str) -> List[_RawBid4AssetsListing]:
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        # Attempt to parse JSON embedded in script tags (Nuxt / Angular style)
        for script in soup.find_all("script"):
            if not script.string:
                continue
            if "__NUXT__" in script.string:
                json_data = self._extract_nuxt_payload(script.string)
                if json_data:
                    listings = self._parse_from_json(json_data)
                    if listings:
                        return listings
        # Fallback to parsing HTML tiles
        return self._parse_from_tiles(soup)

    def _extract_nuxt_payload(self, script_text: str) -> Optional[dict]:
        match = re.search(r"__NUXT__\s*=\s*(\{.*\})", script_text, re.DOTALL)
        if not match:
            return None
        raw = match.group(1)
        # Remove trailing semicolon or script closing tags
        raw = raw.rstrip(";\n ")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def _parse_from_json(self, payload: dict) -> List[_RawBid4AssetsListing]:  # pragma: no cover - depends on live payload
        listings: List[_RawBid4AssetsListing] = []
        items = self._walk_for_key(payload, "listings")
        for item in items:
            if not isinstance(item, list):
                continue
            for entry in item:
                listing = self._build_listing_from_json(entry)
                if listing:
                    listings.append(listing)
        return listings

    def _walk_for_key(self, payload: dict, key: str) -> List[object]:
        matches: List[object] = []
        stack = [payload]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                for k, value in current.items():
                    if k == key:
                        matches.append(value)
                    if isinstance(value, (dict, list)):
                        stack.append(value)
            elif isinstance(current, list):
                stack.extend(current)
        return matches

    def _build_listing_from_json(self, entry: dict) -> Optional[_RawBid4AssetsListing]:
        try:
            identifier = str(entry.get("auctionId") or entry.get("id") or entry.get("auctionid"))
            if not identifier or identifier == "None":
                return None
            title = entry.get("title") or entry.get("name") or "Bid4Assets Listing"
            url_path = entry.get("url") or entry.get("href") or entry.get("link")
            if url_path:
                url = urljoin(self.BASE_URL, url_path)
            else:
                url = urljoin(self.BASE_URL, f"auction/{identifier}")
            minimum_bid = self._to_float(entry.get("minimumBid") or entry.get("minBid") or entry.get("startBid"))
            current_bid = self._to_float(entry.get("currentBid") or entry.get("currentBidAmount"))
            city = self._strip(entry.get("city"))
            county = self._strip(entry.get("county"))
            state = (entry.get("state") or "FL").upper()
            sale_date = self._parse_date(entry.get("startDate") or entry.get("saleDate"))
            sale_type = self._strip(entry.get("auctionType") or entry.get("saleType"))
            acreage = self._to_float(entry.get("acreage") or entry.get("lotSize"))
            property_type = self._strip(entry.get("propertyType") or entry.get("category"))
            status = self._strip(entry.get("status"))
            description = self._strip(entry.get("description"))
            return _RawBid4AssetsListing(
                identifier=identifier,
                title=title,
                url=url,
                minimum_bid=minimum_bid,
                current_bid=current_bid,
                city=city,
                county=county,
                state=state,
                sale_date=sale_date,
                sale_type=sale_type,
                acreage=acreage,
                property_type=property_type,
                status=status,
                description=description,
            )
        except Exception as exc:
            self.log.debug("Unable to parse Bid4Assets JSON entry: %s", exc)
            return None

    def _parse_from_tiles(self, soup: BeautifulSoup) -> List[_RawBid4AssetsListing]:
        listings: List[_RawBid4AssetsListing] = []
        cards = soup.select("[data-auction-id]")
        for card in cards:
            identifier = card.get("data-auction-id")
            if not identifier:
                continue
            title_el = card.select_one(".auction-title, .title, h3, h4")
            title = title_el.get_text(strip=True) if title_el else "Bid4Assets Auction"
            href_el = card.find("a", href=True)
            url = urljoin(self.BASE_URL, href_el["href"]) if href_el else urljoin(self.BASE_URL, f"auction/{identifier}")
            city = self._strip(card.get("data-city"))
            county = self._strip(card.get("data-county"))
            state = (card.get("data-state") or "FL").upper()
            sale_date = self._parse_date(card.get("data-start-date") or card.get("data-sale-date"))
            sale_type = self._strip(card.get("data-sale-type") or card.get("data-auction-type"))
            acreage = self._to_float(card.get("data-acreage") or card.get("data-lot-size"))
            min_bid_text = card.get("data-minimum-bid") or card.get("data-minbid")
            minimum_bid = self._to_float(min_bid_text)
            current_bid = self._to_float(card.get("data-current-bid"))
            property_type = self._strip(card.get("data-property-type"))
            status = self._strip(card.get("data-status"))
            description_el = card.select_one(".auction-description, .description")
            description = description_el.get_text(" ", strip=True) if description_el else None
            listings.append(
                _RawBid4AssetsListing(
                    identifier=identifier,
                    title=title,
                    url=url,
                    minimum_bid=minimum_bid,
                    current_bid=current_bid,
                    city=city,
                    county=county,
                    state=state,
                    sale_date=sale_date,
                    sale_type=sale_type,
                    acreage=acreage,
                    property_type=property_type,
                    status=status,
                    description=description,
                )
            )
        return listings

    def _strip(self, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    def _to_float(self, value: Optional[str | float | int]) -> Optional[float]:
        if value in (None, "", "None"):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        value_str = str(value)
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)", value_str.replace(",", ""))
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
        return None

    def _parse_date(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return date_parser.parse(str(value), fuzzy=True)
        except (ValueError, OverflowError):
            return None
