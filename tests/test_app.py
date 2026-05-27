"""Unit and route tests for the METAR reader app."""

import pytest
from unittest.mock import patch
from app import (
    app,
    celsius_to_fahrenheit,
    knots_to_mph,
    degrees_to_cardinal,
    decode_sky,
    decode_weather,
    decode_metar,
)

# ---------------------------------------------------------------------------
# Shared mock METAR data
# ---------------------------------------------------------------------------

# Realistic METAR record as returned by the aviationweather.gov API.
MOCK_METAR_VFR = {
    "icaoId": "KSFO",
    "name": "San Francisco Intl, CA, US",
    "obsTime": 1748343360,  # 2025-05-27 09:56 UTC
    "temp": 11.1,
    "dewp": 8.9,
    "wdir": 240,
    "wspd": 3,
    "wgst": None,
    "visib": "10+",
    "clouds": [{"cover": "FEW", "base": 800}],
    "wxString": None,
    "altim": 1007.5,
    "fltCat": "VFR",
    "rawOb": "METAR KSFO 270956Z 24003KT 10SM FEW008 11/09 A2976 RMK AO2",
}

MOCK_METAR_IFR = {
    "icaoId": "KSFO",
    "name": "San Francisco Intl, CA, US",
    "obsTime": 1748343360,
    "temp": 10.0,
    "dewp": 9.5,
    "wdir": 270,
    "wspd": 15,
    "wgst": 25,
    "visib": 0.5,
    "clouds": [{"cover": "OVC", "base": 200}],
    "wxString": "FG",
    "altim": 1010.0,
    "fltCat": "IFR",
    "rawOb": "METAR KSFO 270956Z 27015G25KT 1/2SM FG OVC002 10/09 A2982",
}

MOCK_METAR_THUNDERSTORM = {
    "icaoId": "KJFK",
    "name": "New York/JF Kennedy Intl, NY, US",
    "obsTime": 1748343360,
    "temp": 22.0,
    "dewp": 18.0,
    "wdir": 180,
    "wspd": 20,
    "wgst": 35,
    "visib": 2,
    "clouds": [{"cover": "BKN", "base": 1500}, {"cover": "OVC", "base": 3000}],
    "wxString": "+TSRA",
    "altim": 1005.0,
    "fltCat": "IFR",
    "rawOb": "METAR KJFK 270956Z 18020G35KT 2SM +TSRA BKN015 OVC030 22/18 A2970",
}


# ---------------------------------------------------------------------------
# Unit conversions
# ---------------------------------------------------------------------------

class TestConversions:
    def test_celsius_to_fahrenheit_freezing(self):
        assert celsius_to_fahrenheit(0) == 32

    def test_celsius_to_fahrenheit_boiling(self):
        assert celsius_to_fahrenheit(100) == 212

    def test_celsius_to_fahrenheit_negative(self):
        assert celsius_to_fahrenheit(-40) == -40

    def test_celsius_to_fahrenheit_rounds(self):
        assert celsius_to_fahrenheit(11.1) == 52

    def test_knots_to_mph_zero(self):
        assert knots_to_mph(0) == 0

    def test_knots_to_mph_rounds(self):
        assert knots_to_mph(10) == 12

    def test_knots_to_mph_gale(self):
        assert knots_to_mph(35) == 40


# ---------------------------------------------------------------------------
# Cardinal direction
# ---------------------------------------------------------------------------

class TestDegreesToCardinal:
    def test_north(self):
        assert degrees_to_cardinal(0) == "North"

    def test_north_wraps_from_360(self):
        assert degrees_to_cardinal(360) == "North"

    def test_east(self):
        assert degrees_to_cardinal(90) == "East"

    def test_south(self):
        assert degrees_to_cardinal(180) == "South"

    def test_west(self):
        assert degrees_to_cardinal(270) == "West"

    def test_northeast(self):
        assert degrees_to_cardinal(45) == "NE"

    def test_none_returns_variable(self):
        assert degrees_to_cardinal(None) == "variable"


# ---------------------------------------------------------------------------
# Sky condition decoding
# ---------------------------------------------------------------------------

class TestDecodeSky:
    def test_empty_list_is_clear(self):
        assert decode_sky([]) == "clear skies"

    def test_none_is_clear(self):
        assert decode_sky(None) == "clear skies"

    def test_skc(self):
        assert decode_sky([{"cover": "SKC"}]) == "clear skies"

    def test_few_with_base(self):
        result = decode_sky([{"cover": "FEW", "base": 800}])
        assert "few clouds" in result
        assert "800 ft" in result

    def test_overcast(self):
        result = decode_sky([{"cover": "OVC", "base": 200}])
        assert "overcast" in result
        assert "200 ft" in result

    def test_multiple_layers(self):
        layers = [{"cover": "BKN", "base": 1500}, {"cover": "OVC", "base": 3000}]
        result = decode_sky(layers)
        assert ";" in result
        assert "1,500 ft" in result
        assert "3,000 ft" in result

    def test_skc_has_no_altitude(self):
        # Clear-sky codes should not show an altitude even if the API sends one.
        result = decode_sky([{"cover": "SKC", "base": 0}])
        assert "ft" not in result


# ---------------------------------------------------------------------------
# Present-weather decoding
# ---------------------------------------------------------------------------

class TestDecodeWeather:
    def test_none_returns_none(self):
        assert decode_weather(None) is None

    def test_empty_string_returns_none(self):
        assert decode_weather("") is None

    def test_rain(self):
        assert "rain" in decode_weather("RA")

    def test_light_rain(self):
        result = decode_weather("-RA")
        assert "light" in result
        assert "rain" in result

    def test_heavy_thunderstorm_rain(self):
        result = decode_weather("+TSRA")
        assert "heavy" in result
        assert "thunderstorm" in result
        assert "rain" in result

    def test_fog(self):
        assert "fog" in decode_weather("FG")

    def test_snow(self):
        assert "snow" in decode_weather("SN")

    def test_multiple_phenomena(self):
        # Both rain and mist should appear.
        result = decode_weather("RA BR")
        assert "rain" in result
        assert "mist" in result

    def test_freezing_rain(self):
        result = decode_weather("FZRA")
        assert "freezing" in result
        assert "rain" in result


# ---------------------------------------------------------------------------
# Full METAR decoding
# ---------------------------------------------------------------------------

class TestDecodeMetar:
    def test_returns_none_for_empty_data(self):
        assert decode_metar(None) is None
        assert decode_metar({}) is None

    def test_station(self):
        report = decode_metar(MOCK_METAR_VFR)
        assert report["station"] == "KSFO"

    def test_airport_name(self):
        report = decode_metar(MOCK_METAR_VFR)
        assert report["airport_name"] == "San Francisco Intl, CA, US"

    def test_temperature_formatted(self):
        report = decode_metar(MOCK_METAR_VFR)
        assert "52°F" in report["temperature"]
        assert "11.1°C" in report["temperature"]

    def test_dewpoint_formatted(self):
        report = decode_metar(MOCK_METAR_VFR)
        assert "°F" in report["dewpoint"]

    def test_humidity_feel_humid(self):
        # temp=11.1, dewp=8.9 → spread=2.2 → "humid"
        report = decode_metar(MOCK_METAR_VFR)
        assert report["humidity_feel"] == "humid"

    def test_humidity_feel_very_humid(self):
        data = {**MOCK_METAR_IFR, "temp": 10.0, "dewp": 9.5}  # spread=0.5
        report = decode_metar(data)
        assert "very humid" in report["humidity_feel"]

    def test_wind_with_direction(self):
        report = decode_metar(MOCK_METAR_VFR)
        assert "mph" in report["wind"]
        assert "WSW" in report["wind"]  # 240° → WSW

    def test_wind_with_gust(self):
        report = decode_metar(MOCK_METAR_IFR)
        assert "gusting" in report["wind"]

    def test_wind_calm(self):
        data = {**MOCK_METAR_VFR, "wspd": 0}
        report = decode_metar(data)
        assert report["wind"] == "Calm"

    def test_visibility_excellent(self):
        report = decode_metar(MOCK_METAR_VFR)
        assert "10+" in report["visibility"]
        assert "excellent" in report["visibility"]

    def test_visibility_very_low(self):
        report = decode_metar(MOCK_METAR_IFR)
        assert "very low" in report["visibility"]

    def test_sky_decoded(self):
        report = decode_metar(MOCK_METAR_VFR)
        assert "few clouds" in report["sky"].lower()
        assert "800 ft" in report["sky"]

    def test_weather_phenomena_present(self):
        report = decode_metar(MOCK_METAR_IFR)
        assert "fog" in report["weather"].lower()

    def test_weather_phenomena_absent(self):
        report = decode_metar(MOCK_METAR_VFR)
        assert "weather" not in report

    def test_heavy_thunderstorm_weather(self):
        report = decode_metar(MOCK_METAR_THUNDERSTORM)
        assert "heavy" in report["weather"].lower()
        assert "thunderstorm" in report["weather"].lower()

    def test_altimeter_in_inhg(self):
        report = decode_metar(MOCK_METAR_VFR)
        assert "inHg" in report["altimeter"]

    def test_flight_category_vfr(self):
        report = decode_metar(MOCK_METAR_VFR)
        assert report["flight_cat_class"] == "vfr"
        assert "VFR" in report["flight_category"]

    def test_flight_category_ifr(self):
        report = decode_metar(MOCK_METAR_IFR)
        assert report["flight_cat_class"] == "ifr"

    def test_summary_present(self):
        report = decode_metar(MOCK_METAR_VFR)
        assert report["summary"].endswith(".")

    def test_raw_metar_preserved(self):
        report = decode_metar(MOCK_METAR_VFR)
        assert report["raw"] == MOCK_METAR_VFR["rawOb"]

    def test_multiple_cloud_layers(self):
        report = decode_metar(MOCK_METAR_THUNDERSTORM)
        assert ";" in report["sky"]  # two layers separated by semicolon

    def test_cover_fallback_when_no_clouds_key(self):
        # API sometimes omits the clouds array and uses a top-level cover field.
        data = {**MOCK_METAR_VFR, "clouds": None, "cover": "SKC"}
        report = decode_metar(data)
        assert "clear" in report["sky"].lower()


# ---------------------------------------------------------------------------
# Flask route tests
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestRoutes:
    def test_homepage_returns_html(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert b"METAR" in response.data

    def test_weather_missing_param_returns_400(self, client):
        response = client.get("/weather")
        assert response.status_code == 400
        assert b"airport code" in response.data

    def test_weather_invalid_code_returns_400(self, client):
        response = client.get("/weather?airport=INVALID!!")
        assert response.status_code == 400

    def test_weather_valid_airport_returns_report(self, client):
        with patch("app.fetch_metar", return_value=[MOCK_METAR_VFR]):
            response = client.get("/weather?airport=KSFO")
        assert response.status_code == 200
        data = response.get_json()
        assert data["station"] == "KSFO"
        assert "temperature" in data
        assert "wind" in data

    def test_weather_unknown_airport_returns_404(self, client):
        with patch("app.fetch_metar", return_value=None):
            response = client.get("/weather?airport=ZZZZ")
        assert response.status_code == 404

    def test_weather_api_error_returns_503(self, client):
        with patch("app.fetch_metar", side_effect=Exception("timeout")):
            response = client.get("/weather?airport=KSFO")
        assert response.status_code == 503
