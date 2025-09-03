# Options Scanner (Python)

Simple options scanner using [Polygon.io](https://polygon.io) API.  
This script scans for CALL and PUT options that meet certain filters (price, open interest, and days to expiration).

## Features
- Fetches underlying stock data from Polygon.io
- Retrieves option chain (CALL/PUT)
- Filters based on:
  - Price range (`PRICE_MIN`, `PRICE_MAX`)
  - Open interest (`OI_MIN`)
  - Days to expiration (`DTE_MIN`, `DTE_MAX`)
- Picks ATM options for each expiration
- Displays the top 20 cheapest options by mark price

## Requirements
- Python 3.8+
- `requests` library

Install dependencies:
```bash
pip install requests
