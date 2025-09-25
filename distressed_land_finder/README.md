# Florida Distressed Land Finder

This toolkit pulls together IRS seizure auctions and Florida county tax deed or lien offerings hosted on Bid4Assets so you can zero-in on inexpensive commercial or vacant land opportunities. It is designed for terminal environments such as [iSH](https://ish.app/) on iOS and can export leads into CSVs for additional due diligence workflows.

## Features

- Aggregates two high-value sources:
  - **IRS Seized Real Estate** – scrapes the Treasury auction site for Florida listings, including sale date, deposit and property notes.
  - **Bid4Assets** – extracts Florida county tax deed / tax lien auctions that commonly arise from delinquent property taxes.
- Normalizes listings into a single schema with acreage, minimum bid, sale date, location, status and descriptive tags.
- Ranks leads with a scoring model that favors low minimum bids, larger acreage, commercial designations and imminent sale dates.
- Powerful filtering options (price ceilings, minimum acreage, county whitelists, sale type or keyword filtering).
- Optional interactive inspection mode for drilling into the highest-ranked properties without leaving the terminal.
- Caching layer to avoid re-downloading large listing pages during repeated runs.
- Bundled demo dataset for offline experimentation.

## Installation

1. Ensure Python 3.10+ is available in your iSH or Linux environment (`python3 --version`).
2. Install dependencies (recommended inside a virtual environment):

   ```bash
   pip install requests beautifulsoup4 python-dateutil rich
   ```

   The tool gracefully falls back to plain-text tables when `rich` is not installed, but `rich` provides a nicer TUI experience.

3. Copy the `distressed_land_finder` directory to your working project or keep it inside this repository.

## Quick start

Run the CLI directly from the repository root:

```bash
python -m distressed_land_finder.cli --demo
```

The `--demo` flag loads bundled sample listings so you can explore the interface without hitting live endpoints.

To fetch real-time Florida opportunities (requires internet access):

```bash
python -m distressed_land_finder.cli --max-price 200000 --min-acreage 0.5 --counties "Duval,Miami-Dade"
```

### Useful flags

- `--max-price` – Filter out listings whose minimum bid exceeds the specified dollar amount.
- `--min-acreage` – Require listings to meet a minimum acreage threshold.
- `--counties` – Focus on specific Florida counties (comma separated).
- `--tags` – Require tags such as `IRS`, `Tax Deed`, or `Commercial` to be present.
- `--sources` – Choose between `irs` and `bid4assets` connectors (e.g. `--sources irs`).
- `--export leads.csv` – Export the filtered list into a CSV for use in spreadsheets or CRM tools.
- `--interactive` – After displaying the top leads, drop into a prompt where you can type the row number to see detailed information.
- `--skip-cache` – Force refresh of every source instead of using cached pages.

### Interactive mode commands

When running with `--interactive`, enter the numeric row ID to view the full record, or type `q` to exit.

## How it works

1. Each source implementation (see `sources/irs.py` and `sources/bid4assets.py`) downloads and parses the respective provider's public listings.
2. Listings are normalized into a shared data structure (`PropertyListing`) so they can be filtered and ranked uniformly.
3. The scoring engine prioritizes low-cost, land-centric, commercial and soon-to-expire opportunities, producing a sortable score.
4. Results are presented via `rich` tables or plain text and can optionally be exported to CSV.

## Extending the toolkit

- Add new connectors by subclassing the pattern in `distressed_land_finder/sources/` and registering them in `SOURCES_REGISTRY` inside `cli.py`.
- Adjust the scoring heuristics in `filters.py` if you prefer different weighting (e.g., favoring acreage over bid price).
- Create cron jobs or launch agents that run the CLI with `--export` to keep a rolling CSV of upcoming auctions.

## Troubleshooting

- **403 or 503 HTTP errors** – Some auction platforms apply rate limits or block unknown user agents. The bundled `HttpClient` already spoofs a desktop browser, but you may still need to rerun or add your own headers / proxies via code modifications.
- **No listings returned** – Check internet connectivity, confirm the site has active auctions, or run with `--verbose` to see diagnostic logs.
- **Certificate issues on iSH** – Install `ca-certificates` within Alpine (`apk add ca-certificates`) and rerun.

## License

This folder is distributed under the same license as the parent repository. Please respect each data source's terms of service and confirm auction details with the respective county or federal agency before bidding.
