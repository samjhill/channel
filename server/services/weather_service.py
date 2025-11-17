"""
Weather service for fetching and caching current weather data.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import logging
import os
import subprocess
import time
import json
from typing import Optional

try:
    import requests
except ImportError:
    requests = None

# Try multiple possible config paths
_config_paths = [
    Path("/app/config/weather_bumpers.json"),  # Docker volume mount
    Path(__file__).parent.parent / "config" / "weather_bumpers.json",  # Relative to this file
]
CONFIG_PATH = None
for path in _config_paths:
    if path.exists():
        CONFIG_PATH = path
        break
if CONFIG_PATH is None:
    CONFIG_PATH = _config_paths[0]  # Default to first path

API_KEY_FILE = CONFIG_PATH.parent / ".weather_api_key"
CONTAINER_PATH = Path("/app/config/.weather_api_key")
DEFAULT_CONTAINER_NAME = os.environ.get("TVCHANNEL_CONTAINER_NAME", "tvchannel")
LOGGER = logging.getLogger(__name__)


@dataclass
class WeatherInfo:
    temperature: float
    feels_like: float
    condition: str
    city: str
    region: str
    country: str


_cache = {
    "timestamp": 0.0,
    "data": None,  # type: Optional[WeatherInfo]
}


def load_weather_config() -> dict:
    """Load weather bumper configuration from JSON file."""
    if not CONFIG_PATH.exists():
        return {"enabled": False}
    
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_stored_api_key() -> Optional[str]:
    """Load API key from the persistent secret file if present."""
    try:
        if API_KEY_FILE.exists():
            key = API_KEY_FILE.read_text(encoding="utf-8").strip()
            return key or None
    except Exception as exc:
        LOGGER.warning("Failed to read weather API key file: %s", exc)
    return None


def store_api_key(value: str) -> None:
    """Persist API key to the secret file."""
    try:
        API_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        API_KEY_FILE.write_text(value.strip(), encoding="utf-8")
        LOGGER.info("Stored weather API key at %s", API_KEY_FILE)
    except Exception as exc:
        LOGGER.error("Failed to store weather API key: %s", exc)
        raise

    # Best-effort sync: if running outside the container, copy the key into it
    container_name = os.environ.get("TVCHANNEL_CONTAINER_NAME", DEFAULT_CONTAINER_NAME)
    if container_name:
        try:
            if Path("/.dockerenv").exists():
                # Already inside container; nothing to sync
                return
            subprocess.run(
                [
                    "docker",
                    "cp",
                    str(API_KEY_FILE),
                    f"{container_name}:{CONTAINER_PATH}",
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
            )
            LOGGER.info(
                "Synced weather API key to container '%s' at %s",
                container_name,
                CONTAINER_PATH,
            )
        except Exception as exc:
            LOGGER.warning(
                "Unable to sync weather API key to container '%s': %s",
                container_name,
                exc,
            )


def get_current_weather() -> Optional[WeatherInfo]:
    """
    Returns current weather for the configured location, or None if disabled,
    misconfigured, or if the API call fails.
    
    Uses an in-memory cache with TTL from config.
    """
    cfg = load_weather_config()
    if not cfg.get("enabled", True):
        return None
    
    ttl_seconds = cfg.get("cache_ttl_minutes", 7) * 60
    now = time.time()
    
    # Check cache first
    if _cache["data"] is not None and now - _cache["timestamp"] < ttl_seconds:
        return _cache["data"]
    
    # Cache expired or empty, need to fetch
    if requests is None:
        return None
    
    api_var = cfg.get("api_key_env_var", "HBN_WEATHER_API_KEY")
    api_key = os.getenv(api_var)
    if not api_key:
        api_key = cfg.get("api_key")
    if not api_key:
        api_key = load_stored_api_key()
    if not api_key:
        return None
    
    location = cfg.get("location", {})
    lat = location.get("lat")
    lon = location.get("lon")
    
    if lat is None or lon is None:
        return None
    
    units = cfg.get("units", "imperial")
    
    try:
        resp = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"lat": lat, "lon": lon, "appid": api_key, "units": units},
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None
    
    weather_list = data.get("weather", [])
    if not weather_list:
        return None
    
    condition = weather_list[0].get("description", "").title()
    main_data = data.get("main", {})
    temp = float(main_data.get("temp", 0))
    feels = float(main_data.get("feels_like", temp))
    
    info = WeatherInfo(
        temperature=temp,
        feels_like=feels,
        condition=condition,
        city=location.get("city", "Unknown"),
        region=location.get("region", ""),
        country=location.get("country", ""),
    )
    
    # Update cache
    _cache["timestamp"] = now
    _cache["data"] = info
    
    return info

