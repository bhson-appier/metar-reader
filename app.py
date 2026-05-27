from flask import Flask, render_template, request, jsonify
import urllib.request
import urllib.error
import ssl
import json
import re
from datetime import datetime, timezone

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

app = Flask(__name__)

METAR_API = "https://aviationweather.gov/api/data/metar?ids={}&format=json"


def fetch_metar(airport_code):
    url = METAR_API.format(airport_code.upper().strip())
    req = urllib.request.Request(url, headers={"User-Agent": "METAR-Reader/1.0"})
    with urllib.request.urlopen(req, timeout=10, context=_ssl_ctx) as response:
        body = response.read().decode().strip()
    if not body:
        return None
    return json.loads(body)


def celsius_to_fahrenheit(c):
    return round(c * 9 / 5 + 32)


def knots_to_mph(kt):
    return round(kt * 1.15078)


def degrees_to_cardinal(deg):
    if deg is None:
        return "variable"
    directions = ["North", "NNE", "NE", "ENE", "East", "ESE", "SE", "SSE",
                  "South", "SSW", "SW", "WSW", "West", "WNW", "NW", "NNW"]
    idx = round(deg / 22.5) % 16
    return directions[idx]


def decode_sky(sky_condition):
    cover_map = {
        "SKC": "clear skies",
        "CLR": "clear skies",
        "CAVOK": "clear skies, excellent visibility",
        "NSC": "no significant clouds",
        "FEW": "a few clouds",
        "SCT": "scattered clouds",
        "BKN": "mostly cloudy (broken)",
        "OVC": "overcast",
        "VV": "vertical visibility (fog/obscuration)",
    }
    results = []
    if not sky_condition:
        return "clear skies"
    for layer in sky_condition:
        cover = layer.get("cover", "")
        base = layer.get("base")
        text = cover_map.get(cover, cover)
        if base and cover not in ("SKC", "CLR", "CAVOK", "NSC"):
            text += f" at {base:,} ft"
        results.append(text)
    return "; ".join(results) if results else "clear skies"


def decode_weather(wx_string):
    if not wx_string:
        return None

    intensity_map = {"-": "light", "+": "heavy", "VC": "nearby"}
    descriptor_map = {
        "MI": "shallow", "PR": "partial", "BC": "patches of",
        "DR": "low drifting", "BL": "blowing", "SH": "showers of",
        "TS": "thunderstorm with", "FZ": "freezing",
    }
    precip_map = {
        "DZ": "drizzle", "RA": "rain", "SN": "snow", "SG": "snow grains",
        "IC": "ice crystals", "PL": "ice pellets", "GR": "hail",
        "GS": "small hail", "UP": "unknown precipitation",
    }
    obscuration_map = {
        "BR": "mist", "FG": "fog", "FU": "smoke", "VA": "volcanic ash",
        "DU": "dust", "SA": "sand", "HZ": "haze", "PY": "spray",
    }
    other_map = {
        "PO": "dust whirls", "SQ": "squalls", "FC": "funnel cloud/tornado",
        "SS": "sandstorm", "DS": "duststorm",
    }

    all_phen = {**precip_map, **obscuration_map, **other_map}
    parts = []
    for token in wx_string.split():
        i = 0
        intensity = ""
        if token and token[0] in ("-", "+"):
            intensity = intensity_map.get(token[0], "") + " "
            i = 1
        elif token[:2] == "VC":
            intensity = "nearby "
            i = 2

        descriptor = ""
        if token[i:i+2] in descriptor_map:
            descriptor = descriptor_map[token[i:i+2]] + " "
            i += 2

        phenomena = []
        while i < len(token):
            code = token[i:i+2]
            if code in all_phen:
                phenomena.append(all_phen[code])
                i += 2
            else:
                i += 1

        if phenomena:
            parts.append(intensity + descriptor + " and ".join(phenomena))

    return ", ".join(parts) if parts else None


def decode_metar(data):
    if not data:
        return None

    report = {}

    # Station
    report["station"] = data.get("icaoId", data.get("stationId", "Unknown"))
    airport_name = data.get("name")
    if airport_name:
        report["airport_name"] = airport_name

    # Observation time
    obs_time = data.get("obsTime")
    if obs_time:
        try:
            dt = datetime.fromtimestamp(obs_time, tz=timezone.utc)
            report["time"] = dt.strftime("%B %d, %Y at %H:%M UTC")
        except Exception:
            report["time"] = str(obs_time)

    # Temperature
    temp_c = data.get("temp")
    if temp_c is not None:
        temp_f = celsius_to_fahrenheit(temp_c)
        report["temperature"] = f"{temp_f}°F ({temp_c}°C)"
        report["temp_f"] = temp_f

    # Dewpoint and humidity feel
    dewp_c = data.get("dewp")
    if dewp_c is not None and temp_c is not None:
        dewp_f = celsius_to_fahrenheit(dewp_c)
        report["dewpoint"] = f"{dewp_f}°F ({dewp_c}°C)"
        spread = temp_c - dewp_c
        if spread <= 2:
            report["humidity_feel"] = "very humid / foggy conditions possible"
        elif spread <= 5:
            report["humidity_feel"] = "humid"
        elif spread <= 10:
            report["humidity_feel"] = "moderately humid"
        else:
            report["humidity_feel"] = "dry"

    # Wind
    wdir = data.get("wdir")
    wspd = data.get("wspd")
    wgst = data.get("wgst")
    if wspd is not None:
        if wspd == 0:
            report["wind"] = "Calm"
        else:
            speed_mph = knots_to_mph(wspd)
            direction = degrees_to_cardinal(wdir) if wdir not in (None, 0) else "variable"
            report["wind"] = f"{speed_mph} mph from the {direction}"
            if wgst:
                gust_mph = knots_to_mph(wgst)
                report["wind"] += f", gusting to {gust_mph} mph"

    # Visibility — API returns "10+" as a string or a numeric value
    visib_raw = data.get("visib")
    if visib_raw is not None:
        try:
            visib = float(str(visib_raw).replace("+", ""))
            if "+" in str(visib_raw) or visib >= 10:
                report["visibility"] = "10+ miles (excellent)"
            elif visib >= 5:
                report["visibility"] = f"{visib_raw} miles (good)"
            elif visib >= 3:
                report["visibility"] = f"{visib_raw} miles (moderate)"
            elif visib >= 1:
                report["visibility"] = f"{visib_raw} miles (poor)"
            else:
                report["visibility"] = f"{visib_raw} mile(s) (very low — use caution)"
        except ValueError:
            report["visibility"] = str(visib_raw)

    # Sky / clouds — use clouds array; fall back to cover field
    clouds = data.get("clouds")
    if not clouds:
        cover = data.get("cover")
        if cover:
            clouds = [{"cover": cover}]
    report["sky"] = decode_sky(clouds).capitalize()

    # Weather phenomena
    wx = data.get("wxString")
    wx_decoded = decode_weather(wx)
    if wx_decoded:
        report["weather"] = wx_decoded.capitalize()

    # Altimeter — API returns hPa, convert to inHg
    altim = data.get("altim")
    if altim is not None:
        inhg = round(altim * 0.02953, 2)
        report["altimeter"] = f"{inhg} inHg"

    # Flight category — field is "fltCat" in the API
    flt_cat = data.get("fltCat", data.get("flightCategory"))
    cat_map = {
        "VFR": ("VFR — Visual Flight Rules (great flying weather)", "vfr"),
        "MVFR": ("MVFR — Marginal VFR (acceptable, some caution needed)", "mvfr"),
        "IFR": ("IFR — Instrument Flight Rules (low visibility/clouds)", "ifr"),
        "LIFR": ("LIFR — Low IFR (very poor conditions)", "lifr"),
    }
    if flt_cat in cat_map:
        report["flight_category"], report["flight_cat_class"] = cat_map[flt_cat]

    # Plain-English summary
    summary_parts = []
    sky_lower = report.get("sky", "").lower()
    if "clear" in sky_lower or "few" in sky_lower:
        summary_parts.append("mostly sunny")
    elif "scattered" in sky_lower:
        summary_parts.append("partly cloudy")
    elif "broken" in sky_lower or "overcast" in sky_lower:
        summary_parts.append("cloudy")

    if "weather" in report:
        summary_parts.append(report["weather"].lower())

    if "temp_f" in report:
        summary_parts.append(f"{report['temp_f']}°F")

    if "wind" in report:
        wind_val = report["wind"]
        if wind_val.lower() == "calm":
            summary_parts.append("calm winds")
        else:
            summary_parts.append(f"winds {wind_val}")

    if summary_parts:
        joined = ", ".join(summary_parts)
        report["summary"] = joined[0].upper() + joined[1:] + "."

    # Raw METAR
    report["raw"] = data.get("rawOb", "")

    return report


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/weather", methods=["GET"])
def weather():
    code = request.args.get("airport", "").strip().upper()
    if not code:
        return jsonify({"error": "Please enter an airport code."}), 400
    if not re.match(r"^[A-Z0-9]{3,4}$", code):
        return jsonify({"error": "Invalid airport code. Use 3–4 letter ICAO codes (e.g. KHIO, KSFO)."}), 400

    try:
        raw_data = fetch_metar(code)
    except urllib.error.HTTPError as e:
        return jsonify({"error": f"Airport not found or API error ({e.code})."}), 404
    except Exception as e:
        return jsonify({"error": f"Could not reach weather service: {e}"}), 503

    if not raw_data:
        return jsonify({"error": f"No METAR data found for {code}. Check the airport code."}), 404

    report = decode_metar(raw_data[0] if isinstance(raw_data, list) else raw_data)
    if not report:
        return jsonify({"error": "Could not decode METAR data."}), 500

    return jsonify(report)


if __name__ == "__main__":
    app.run(debug=True)
