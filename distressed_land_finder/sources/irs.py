from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Iterable, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from ..http import HttpClient
from .base import PropertyListing, merge_tags


class IRSRealEstateSource:
    slug = "irs"
    title = "IRS Seized Real Estate"

    BASE_URL = "https://www.treasury.gov/auctions/irs/"
    INDEX_PAGES = [
        urljoin(BASE_URL, "auctions1.shtml"),
        urljoin(BASE_URL, "auctions2.shtml"),
    ]

    def __init__(self, *, client: Optional[HttpClient] = None, state: str = "FL") -> None:
        self.client = client or HttpClient()
        self.log = logging.getLogger(self.__class__.__name__)
        self.state = state.upper()

    def fetch_listings(self) -> Iterable[PropertyListing]:
        detail_urls = self._discover_state_urls()
        listings: List[PropertyListing] = []
        for url in sorted(detail_urls):
            try:
                listing = self._parse_listing(url)
            except Exception as exc:  # pragma: no cover - best-effort network parsing
                self.log.warning("Failed to parse IRS listing at %s: %s", url, exc)
                continue
            if listing:
                listings.append(listing)
        return listings

    def _discover_state_urls(self) -> List[str]:
        pattern = re.compile(rf"\b{self.state}\b", re.IGNORECASE)
        urls: set[str] = set()
        for index_url in self.INDEX_PAGES:
            try:
                html = self.client.get(index_url).text
            except Exception as exc:  # pragma: no cover - network failure
                self.log.warning("Unable to fetch IRS index %s: %s", index_url, exc)
                continue
            soup = BeautifulSoup(html, "html.parser")
            for link in soup.find_all("a", href=True):
                href = link["href"].strip()
                text = " ".join(link.stripped_strings)
                if not href.lower().endswith((".htm", ".html")):
                    continue
                if pattern.search(text) or self.state.lower() in href.lower():
                    urls.add(urljoin(self.BASE_URL, href))
        return list(urls)

    def _parse_listing(self, url: str) -> Optional[PropertyListing]:
        response = self.client.get(url)
        soup = BeautifulSoup(response.text, "html.parser")
        title = self._extract_title(soup, url)
        raw_text = "\n".join(soup.stripped_strings)

        sale_date = self._extract_date(raw_text)
        minimum_bid = self._extract_currency(raw_text, ["Minimum Bid", "Min Bid"])
        deposit = self._extract_currency(raw_text, ["Deposit", "Minimum Deposit"])
        address, city, county, zip_code = self._extract_location(raw_text)
        acreage = self._extract_acreage(raw_text)
        property_type = self._guess_property_type(title, raw_text)
        description = self._extract_description(soup)

        tags = merge_tags(["IRS"], ["Seizure"], ["Federal"], ["Commercial" if "commercial" in (property_type or "").lower() else ""])
        tags = [tag for tag in tags if tag]

        external_id = self._extract_external_id(url)

        return PropertyListing(
            source=self.title,
            external_id=external_id,
            title=title,
            url=url,
            state=self.state,
            county=county,
            city=city,
            address=address,
            zip_code=zip_code,
            sale_date=sale_date,
            sale_type="Federal seizure auction",
            status="Active",
            minimum_bid=minimum_bid,
            deposit=deposit,
            acreage=acreage,
            property_type=property_type,
            tags=tags,
            description=description,
            raw_data={"source": "irs", "page_url": url},
        )

    def _extract_title(self, soup: BeautifulSoup, url: str) -> str:
        title_el = soup.find("h1") or soup.find("h2")
        if title_el:
            return title_el.get_text(strip=True)
        strong_el = soup.find("strong")
        if strong_el:
            return strong_el.get_text(strip=True)
        return f"IRS Auction - {url.split('/')[-1]}"

    def _extract_date(self, text: str) -> Optional[datetime]:
        match = re.search(r"Sale Date(?: & Time)?:\s*([^\n]+)", text, re.IGNORECASE)
        if not match:
            match = re.search(r"Date:\s*([^\n]+)", text, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            try:
                return date_parser.parse(candidate, fuzzy=True)
            except (ValueError, OverflowError):
                return None
        return None

    def _extract_currency(self, text: str, labels: List[str]) -> Optional[float]:
        for label in labels:
            pattern = re.compile(rf"{label}[^$]*\$([0-9,]+(?:\.[0-9]+)?)", re.IGNORECASE)
            match = pattern.search(text)
            if match:
                raw = match.group(1)
                try:
                    return float(raw.replace(",", ""))
                except ValueError:
                    continue
        return None

    def _extract_location(self, text: str) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        match = re.search(r"Property (?:Location|Address):\s*([^\n]+)", text, re.IGNORECASE)
        address_line = match.group(1).strip() if match else None
        city = county = zip_code = None
        if address_line:
            parts = [part.strip() for part in re.split(r",| - ", address_line) if part.strip()]
            if parts:
                city = parts[-2] if len(parts) >= 2 else parts[-1]
                if "FL" in parts[-1]:
                    zip_match = re.search(r"(\d{5})", parts[-1])
                    zip_code = zip_match.group(1) if zip_match else None
                county_match = re.search(r"([A-Za-z]+) County", text)
                if county_match:
                    county = county_match.group(1).strip()
            address_line = ", ".join(parts)
        return address_line, city, county, zip_code

    def _extract_acreage(self, text: str) -> Optional[float]:
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(?:acre|acres)\b", text, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
        return None

    def _guess_property_type(self, title: str, text: str) -> Optional[str]:
        combined = f"{title}\n{text}".lower()
        if "commercial" in combined:
            return "Commercial Property"
        if "industrial" in combined:
            return "Industrial Property"
        if any(word in combined for word in ["vacant", "land", "lot", "acre"]):
            return "Vacant Land"
        if "residential" in combined:
            return "Residential"
        return None

    def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        if not paragraphs:
            paragraphs = [soup.get_text(" ", strip=True)]
        return "\n".join(paragraphs[:5]) if paragraphs else None

    def _extract_external_id(self, url: str) -> str:
        match = re.search(r"([a-z0-9]+)\.htm", url, re.IGNORECASE)
        if match:
            return match.group(1)
        return url
