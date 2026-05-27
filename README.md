# METAR Reader

A Flask web app that fetches live METAR reports and translates aviation weather into plain English.

## What it does

Enter any ICAO airport code (e.g. `KSFO`, `KJFK`, `KHIO`) to get a human-readable weather report including:

- Temperature and dewpoint (°F / °C)
- Wind speed and direction (mph, cardinal)
- Visibility with qualitative rating
- Sky conditions and cloud layers
- Weather phenomena (rain, snow, fog, thunderstorms, etc.)
- Altimeter setting (inHg)
- Flight category: VFR / MVFR / IFR / LIFR
- Plain-English summary

Data is sourced from the [aviationweather.gov](https://aviationweather.gov) API.

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv run app.py
```

Then open http://localhost:5000 in your browser.

## ICAO codes

ICAO codes are 4-letter identifiers used globally. In the US, they start with `K` (e.g. `KSFO` for San Francisco, `KJFK` for JFK). Canadian airports start with `C`, UK with `EG`, etc.
