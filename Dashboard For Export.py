"""
Emperor's Daily Dashboard Generator
-----------------------------------
Generates a daily PDF dashboard for reMarkable 2, including calendar events and weather, with robust ICS parsing and upload reliability.
Standardized on icalendar for .ics parsing (Google Calendar compatible).

Features:
- Automation-hardened architecture with graceful degradation
- Emergency dashboard fallback for unattended execution
- Comprehensive error handling and local PDF backup
- Windows Task Scheduler ready with robust .bat script
"""
import sys
import calendar
import shutil
import tempfile
import requests
import json
import time
import logging
import socket
import pytz
import arrow
import icalendar
import uuid as _uuid
import subprocess
import os
import re
from pathlib import Path
from itertools import groupby
from operator import itemgetter
from typing import List, Dict, Any, Optional, Tuple
from jinja2 import Environment, FileSystemLoader
from concurrent.futures import ThreadPoolExecutor
from dateutil.rrule import rrulestr, rruleset, rrule, WEEKLY, MONTHLY, YEARLY, DAILY
from datetime import datetime, timedelta, date, timezone
from weasyprint import HTML
from pypdf import PdfWriter, PdfReader

# ==============================================================================
# ENVIRONMENT LOADING
# ==============================================================================

# Load .env file if it exists
def load_env_file():
    """Load environment variables from .env file"""
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip().strip('"\'')

# Load environment variables immediately
load_env_file()

# ==============================================================================
# CONFIGURATION
# ==============================================================================
def load_calendar_feeds(path: Path) -> list:
    """Loads calendar URLs from a text file, one per line, ignoring comments and blanks."""
    if not path.is_file():
        raise FileNotFoundError(f"Calendar feed file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return [
            line.strip()
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]

class Config:
    CALENDAR_FEEDS_FILE: Path = Path("calendar_feeds.txt")
    ICAL_FEEDS: List[str] = []  # Will be loaded at runtime
    REMARKABLE_IP: str = os.getenv("REMARKABLE_IP", "192.168.1.100")
    REMARKABLE_USER: str = os.getenv("REMARKABLE_USER", "root")
    REMARKABLE_SSH_KEY: Path = Path(os.path.expanduser(os.getenv("REMARKABLE_SSH_KEY", str(Path.home() / ".ssh" / "id_rsa"))))
    BASE_DIR: Path = Path(__file__).resolve().parent
    TEMPLATE_FILE: str = "dashboard_template.html"
    LOG_FILE: Path = BASE_DIR / "dashboard_run.log"
    DOWNLOAD_RETRIES: int = 3
    DOWNLOAD_RETRY_DELAY_SECONDS: int = 5
    REMOTE_COMMAND_TIMEOUT_SECONDS: int = 20
    TIMEZONE_LOCAL_STR: str = os.getenv("TIMEZONE", "Asia/Singapore")
    LOCATIONS: Dict[str, Tuple[float, float]] = {
        "🏠": (float(os.getenv("HOME_LAT", "1.29")), float(os.getenv("HOME_LON", "103.85"))),
        "🏯": (float(os.getenv("WORK_LAT", "1.29")), float(os.getenv("WORK_LON", "103.85"))),
    }
    EPIGRAPH: Optional[Dict[str, str]] = {
        "quote": os.getenv("EPIGRAPH_QUOTE", "The LORD is my strength, and my song, and is become my salvation."),
        "author": os.getenv("EPIGRAPH_AUTHOR", "")
    }
    LOCAL_OUTPUT_PATH: Optional[Path] = Path(os.getenv("LOCAL_OUTPUT_PATH", f"C:/Users/{os.getenv('USERNAME', 'User')}/Documents/Dashboard_Output"))
    MAX_ITEMS_PER_PAGE: int = int(os.getenv("MAX_ITEMS_PER_PAGE", "6"))  # Combined events + tasks per page (reduced from 8 for better note-taking space)
    COVER_IMAGE_PATH: Optional[Path] = Path(os.getenv("COVER_IMAGE_PATH", "cover-image.jpg")) if os.getenv("COVER_IMAGE_PATH") else None
    REMARKABLE_IPS: list = [os.getenv("REMARKABLE_BACKUP_IP", "10.11.99.1"), REMARKABLE_IP]

# ==============================================================================
# LOGGING
# ==============================================================================
def setup_logging() -> None:
    """Configures logging to file and console."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-8s] %(message)s",
        handlers=[
            logging.FileHandler(Config.LOG_FILE, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    logging.getLogger('weasyprint').setLevel(logging.WARNING)

# ==============================================================================
# UTILITY FUNCTIONS
# ==============================================================================
def run_command(command: List[str], timeout: int, input_data: Optional[str] = None, cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    """Run external commands with logging and error handling."""
    logging.info(f"   -> Running command: {' '.join(command)}")
    try:
        return subprocess.run(
            command,
            input=input_data,
            capture_output=True,
            check=True,
            text=True,
            encoding='utf-8',
            timeout=timeout,
            cwd=cwd
        )
    except FileNotFoundError:
        logging.critical(f"Command not found: {command[0]}. Ensure it is installed and in the system's PATH.")
        raise
    except subprocess.CalledProcessError as e:
        logging.error(
            f"Command failed with exit code {e.returncode}:\n"
            f"--- STDOUT ---\n{e.stdout}\n"
            f"--- STDERR ---\n{e.stderr}"
        )
        raise
    except subprocess.TimeoutExpired:
        logging.error(f"Command timed out after {timeout} seconds: {' '.join(command)}")
        raise

def pre_flight_checks() -> None:
    """Verifies that all required external programs and files exist before running."""
    logging.info("Running pre-flight checks...")
    # Check if SSH tools are available for upload
    ssh_available = True
    
    required_tools = ["scp", "ssh"]
    for tool in required_tools:
        if not shutil.which(tool):
            ssh_available = False
            logging.warning(f"⚠️ SSH tool '{tool}' not found in PATH. Upload will be disabled.")
    
    if not Config.REMARKABLE_SSH_KEY.is_file():
        ssh_available = False
        logging.warning(f"⚠️ reMarkable SSH key not found at {Config.REMARKABLE_SSH_KEY}. Upload will be disabled.")
    
    if not ssh_available:
        logging.warning("⚠️ Upload to reMarkable will be skipped due to missing SSH configuration.")
        # Set a global flag to disable upload later
        globals()['UPLOAD_DISABLED'] = True
    else:
        globals()['UPLOAD_DISABLED'] = False
    
    # Check core requirements
    if not (Config.BASE_DIR / Config.TEMPLATE_FILE).is_file():
        raise FileNotFoundError(f"CRITICAL: HTML template not found at {Config.BASE_DIR / Config.TEMPLATE_FILE}")
    
    # Basic config validation for automation reliability
    if not Config.ICAL_FEEDS:
        logging.warning("⚠️ No calendar feeds configured. Dashboard will have no events.")
    if ssh_available and Config.REMARKABLE_IP == "192.168.1.100":
        logging.warning("⚠️ Using default reMarkable IP. Update REMARKABLE_IP in .env file for your device.")
    if Config.LOCAL_OUTPUT_PATH and not os.path.exists(str(Config.LOCAL_OUTPUT_PATH.parent)):
        logging.warning(f"⚠️ Local output directory may not exist: {Config.LOCAL_OUTPUT_PATH}")
    
    logging.info("✅ Pre-flight checks completed.")

# ==============================================================================
# UTILITY FUNCTIONS
# ==============================================================================
def safe_first(lst, default=None):
    """Safely gets the first item from a list, returns default if empty or None."""
    if lst and len(lst) > 0:
        return lst[0]
    return default

# ==============================================================================
# WEATHER
# ==============================================================================
def fetch_weather_for_location(location_data: Tuple[str, Tuple[float, float]]) -> Tuple[str, Dict[str, Any]]:
    """Fetches daily summary and hourly rain forecast for one location."""
    name, (lat, lon) = location_data
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&timezone={Config.TIMEZONE_LOCAL_STR}"
        f"&daily=temperature_2m_max,temperature_2m_min,uv_index_max,weathercode"
        f"&hourly=precipitation_probability,precipitation,temperature_2m,weathercode,cloudcover,wind_speed_10m,wind_gusts_10m"
        f"&forecast_days=2"  # Changed from 1 to 2 for robust next-day data
    )
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        # --- BEGIN: TEMPORARY RAW API DUMP ---
        raw_api_dump_path = Config.BASE_DIR / "weather_api_raw_dump.txt"
        with open(raw_api_dump_path, "a", encoding="utf-8") as f:
            f.write(f"\n--- {name} ---\n")
            f.write(json.dumps(data, indent=2, ensure_ascii=False))
            f.write("\n")
        logging.info(f"Raw weather API response for {name} dumped to {raw_api_dump_path}")
        # --- END: TEMPORARY RAW API DUMP ---
        if 'daily' not in data or 'hourly' not in data:
            logging.warning(f"API response for {name} is missing 'daily' or 'hourly' keys.")
            return name, {}
        logging.info(f"API URL: {url}")
        logging.info(f"API response keys: {list(data.keys())}")
        daily_data = data['daily']
        hourly_data = data['hourly']
        # Use only today's data (index 0) for now, but allow for tomorrow (index 1) if needed
        processed_data = {
            'temp_max': safe_first(daily_data.get('temperature_2m_max')),
            'temp_min': safe_first(daily_data.get('temperature_2m_min')),
            'uv_max': safe_first(daily_data.get('uv_index_max')),
            'weathercode': safe_first(daily_data.get('weathercode')),
            # Removed unsupported daily fields
            'hourly_rain_prob': list(zip(hourly_data.get('time', []), hourly_data.get('precipitation_probability', []))),
            'hourly_precip': list(zip(hourly_data.get('time', []), hourly_data.get('precipitation', []))),
            'hourly_temp': list(zip(hourly_data.get('time', []), hourly_data.get('temperature_2m', []))),
            'hourly_weathercode': list(zip(hourly_data.get('time', []), hourly_data.get('weathercode', []))),
            'hourly_cloudcover': list(zip(hourly_data.get('time', []), hourly_data.get('cloudcover', []))),
            # 'hourly_humidity' removed, as humidity_2m is not supported for Singapore
            'hourly_wind_speed': list(zip(hourly_data.get('time', []), hourly_data.get('wind_speed_10m', []))),
            'hourly_wind_gusts': list(zip(hourly_data.get('time', []), hourly_data.get('wind_gusts_10m', []))),
            # Add tomorrow's data for robust next-day forecast
            'tomorrow_temp_max': daily_data.get('temperature_2m_max')[1] if daily_data.get('temperature_2m_max') and len(daily_data.get('temperature_2m_max')) > 1 else None,
            'tomorrow_temp_min': daily_data.get('temperature_2m_min')[1] if daily_data.get('temperature_2m_min') and len(daily_data.get('temperature_2m_min')) > 1 else None,
            'tomorrow_uv_max': daily_data.get('uv_index_max')[1] if daily_data.get('uv_index_max') and len(daily_data.get('uv_index_max')) > 1 else None,
            'tomorrow_weathercode': daily_data.get('weathercode')[1] if daily_data.get('weathercode') and len(daily_data.get('weathercode')) > 1 else None,
            'tomorrow_date': daily_data.get('time')[1] if daily_data.get('time') and len(daily_data.get('time')) > 1 else None,
        }
        # --- Add air quality extraction ---
        # Try to extract PM2.5, PM10, AQI if present in API response
        air_quality = data.get('current', {})
        # Some APIs may provide air quality in a different structure; adjust as needed
        processed_data['pm2_5'] = air_quality.get('pm2_5') or data.get('pm2_5')
        processed_data['pm10'] = air_quality.get('pm10') or data.get('pm10')
        processed_data['aqi'] = air_quality.get('aqi') or data.get('aqi')
        logging.info(f"Processed data for {name}: {processed_data}")
        return name, processed_data
    except requests.RequestException as e:
        logging.warning(f"Weather fetch failed for {name}: {e}")
        return name, {}
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logging.warning(f"Failed to process weather data for {name}: {e}")
        return name, {}

def get_weather_data() -> Dict[str, Dict[str, Any]]:
    """Fetches weather data for all locations concurrently."""
    logging.info("   -> Fetching weather for all locations concurrently...")
    with ThreadPoolExecutor(max_workers=len(Config.LOCATIONS)) as executor:
        results = list(executor.map(fetch_weather_for_location, Config.LOCATIONS.items()))
    return {name: forecast for name, forecast in results}

def generate_weather_narrative(forecast: Dict[str, Any], for_tomorrow: bool = False) -> str:
    """Generates a human-readable summary of the weather forecast, including peak rain probability if applicable.
    If for_tomorrow is True, uses tomorrow's data if available.
    """
    try:
        # Remove location name from output (handled in template)
        # logging.info("generate_weather_narrative called with forecast: %s", json.dumps(forecast, default=str, indent=2))
        if for_tomorrow:
            temp_min = forecast.get('tomorrow_temp_min')
            temp_max = forecast.get('tomorrow_temp_max')
            code = forecast.get('tomorrow_weathercode')
            uv_max = forecast.get('tomorrow_uv_max')
            tomorrow_date = forecast.get('tomorrow_date')
            try:
                hourly_rain = [(t, p) for t, p in forecast.get('hourly_rain_prob', []) if tomorrow_date and t.startswith(tomorrow_date)]
                hourly_precip = [(t, p) for t, p in forecast.get('hourly_precip', []) if tomorrow_date and t.startswith(tomorrow_date)]
            except (TypeError, AttributeError):
                hourly_rain = []
                hourly_precip = []
            # Only include humidity if present
            hourly_humidity = forecast.get('hourly_humidity', [])
            if hourly_humidity:
                try:
                    hourly_humidity = [(t, h) for t, h in hourly_humidity if tomorrow_date and t.startswith(tomorrow_date)]
                except (TypeError, AttributeError):
                    hourly_humidity = []
            # Rain accumulation for tomorrow
            try:
                rain_accum = sum(p for _, p in hourly_precip if p is not None)
            except (TypeError, ValueError):
                rain_accum = 0
        else:
            temp_min = forecast.get('temp_min')
            temp_max = forecast.get('temp_max')
            code = forecast.get('weathercode')
            uv_max = forecast.get('uv_max')
            hourly_rain = forecast.get('hourly_rain_prob', [])
            hourly_precip = forecast.get('hourly_precip', [])
            hourly_humidity = forecast.get('hourly_humidity', [])
            # Rain accumulation for today
            try:
                rain_accum = sum(p for _, p in hourly_precip if p is not None)
            except (TypeError, ValueError):
                rain_accum = 0

        required_keys = [temp_min, temp_max, code, uv_max]
        if not forecast or not all(k is not None for k in required_keys):
            logging.warning("Weather summary unavailable due to missing keys or empty forecast.")
            return "Weather summary unavailable."

        try:
            temp_summary = f"{round(temp_min)}–{round(temp_max)}°C" if temp_min is not None and temp_max is not None else "Temp data unavailable."
        except (TypeError, ValueError):
            temp_summary = "Temp data unavailable."

        # Weather code mapping
        conditions_map = {
            0: "Clear skies.", 1: "Mainly clear.", 2: "Partly cloudy.", 3: "Overcast.",
            45: "Foggy.", 48: "Foggy.",
            51: "Light drizzle.", 53: "Drizzle.", 55: "Heavy drizzle.",
            61: "Light rain.", 63: "Rain.", 65: "Heavy rain.",
            80: "Showers.", 81: "Showers.", 82: "Heavy showers.",
            95: "Thunderstorms.", 96: "Thunderstorms.", 99: "Thunderstorms."
        }
        try:
            base_condition = conditions_map.get(int(code) if code is not None else 0, "Mixed conditions.")
        except (TypeError, ValueError):
            base_condition = "Mixed conditions."

        # Rain summary (hourly) with error handling
        rain_summary = ""
        peak_rain_info = ""
        rain_windows = []
        rain_periods = []
        peak_day_rain_prob = None
        peak_day_rain_hour = None
        
        try:
            # Focus on daytime hours (7am-7pm)
            daytime_rain = []
            daytime_precip = []
            
            for t, p in hourly_rain:
                try:
                    if p is not None and 7 <= arrow.get(t).hour < 19:
                        daytime_rain.append((arrow.get(t), p))
                except (TypeError, AttributeError):
                    continue
                    
            for t, p in hourly_precip:
                try:
                    if p is not None and 7 <= arrow.get(t).hour < 19:
                        daytime_precip.append((arrow.get(t), p))
                except (TypeError, AttributeError):
                    continue
                    
            # Check for heavy rain (precip ≥ 5mm)
            heavy_rain_hours = [t for t, p in daytime_precip if p >= 5]
            threshold = 40
            current_window = []
            for t, p in daytime_rain:
                if p >= threshold:
                    current_window.append((t, p))
                else:
                    if current_window:
                        rain_windows.append(current_window)
                        current_window = []
            if current_window:
                rain_windows.append(current_window)
                
            # Summarize rain windows
            if rain_windows:
                rain_periods = []
                for window in rain_windows:
                    try:
                        start = window[0][0].format('HH')
                        end = window[-1][0].format('HH')
                        if start == end:
                            rain_periods.append(f"{start}")
                        else:
                            rain_periods.append(f"{start}-{end}")
                    except (AttributeError, IndexError):
                        continue
                rain_summary = f"Rain likely {', '.join(rain_periods)}." if rain_periods else "Rain expected."
            elif heavy_rain_hours:
                try:
                    times = ', '.join(t.format('HH:mm') for t in heavy_rain_hours)
                    rain_summary = f"Heavy rain expected at {times}."
                except (AttributeError, TypeError):
                    rain_summary = "Heavy rain expected."
            elif any(p >= 20 for _, p in daytime_rain):
                rain_summary = "Chance of light showers."
            else:
                rain_summary = "No rain expected."
                
            # Peak rain info
            if daytime_rain:
                try:
                    peak_day_rain_hour, peak_day_rain_prob = max(daytime_rain, key=itemgetter(1))
                    if peak_day_rain_prob >= threshold:
                        peak_rain_info = f"Peak {peak_day_rain_prob}% at {peak_day_rain_hour.format('HH:mm')}."
                except (ValueError, TypeError, AttributeError):
                    pass
        except Exception as e:
            logging.warning(f"Error processing rain data: {e}")
            rain_summary = "Rain data unavailable."

        conditions_summary = rain_summary or base_condition

        # UV summary (number only, no category) with error handling
        uv_summary = ""
        try:
            if uv_max is not None:
                uv_level = int(round(uv_max))
                uv_summary = f"UV {uv_level}."
        except (TypeError, ValueError):
            pass

        # Heat warning with error handling
        heat_warning = ""
        try:
            if temp_max is not None and temp_max >= 34:
                heat_warning = "Very hot. Stay hydrated."
        except (TypeError, ValueError):
            pass

        # Humidity (if available) with error handling
        humidity_summary = ""
        try:
            if hourly_humidity:
                # Average daytime humidity
                daytime_humidity = []
                for t, h in hourly_humidity:
                    try:
                        if h is not None and 7 <= arrow.get(t).hour < 19:
                            daytime_humidity.append(h)
                    except (TypeError, AttributeError):
                        continue
                if daytime_humidity:
                    avg_humidity = round(sum(daytime_humidity) / len(daytime_humidity))
                    humidity_summary = f"Avg humidity: {avg_humidity}%."
        except Exception as e:
            logging.warning(f"Error processing humidity data: {e}")

        # --- New rain narrative format with error handling ---
        # Example: Rain 31.2mm, likely 08-17, 10-16, Peak 100% @ 10
        rain_narrative = ""
        try:
            if rain_periods or peak_day_rain_prob or rain_accum > 0:
                rain_parts = []
                if rain_accum > 0:
                    rain_parts.append(f"Rain {rain_accum:.1f}mm")
                if rain_periods:
                    rain_parts.append("likely " + ", ".join(rain_periods))
                if peak_day_rain_prob and peak_day_rain_hour:
                    try:
                        rain_parts.append(f"Peak {int(round(peak_day_rain_prob))}% @ {peak_day_rain_hour.format('HH')}")
                    except (TypeError, ValueError, AttributeError):
                        pass
                rain_narrative = ", ".join(rain_parts)
            else:
                rain_narrative = "No rain expected."
        except Exception as e:
            logging.warning(f"Error building rain narrative: {e}")
            rain_narrative = "Rain data unavailable."

        # Use semicolons between main sections: temp; rain; uv; heat; humidity
        try:
            summary_parts = [
                temp_summary,
                rain_narrative,
                uv_summary,
                heat_warning,
                humidity_summary
            ]
            # Only include non-empty parts
            summary = "; ".join([part for part in summary_parts if part])
            summary = summary.strip()
            if not summary.endswith("."):
                summary = summary.rstrip("; ") + "."
            return summary
        except Exception as e:
            logging.warning(f"Error building final weather summary: {e}")
            return "Weather summary unavailable."
    except Exception as e:
        logging.error(f"Unexpected error in generate_weather_narrative: {e}")
        return "Weather summary unavailable."

# ==============================================================================
# CALENDAR & EVENTS
# ==============================================================================
EVENT_ICON_KEYWORDS: Dict[str, List[str]] = {
    "👥": ["sync", "meeting", "call", "catch-up", "zoom", "teams", "hangout", "conference", "webinar", "appt", "appointment"],
    "✈️": ["flight", "airport", "flew", "depart", "arrival", "boarding", "gate", "travel", "train", "bus", "mrt", "transport", "commute", "transit"],
    "🍴": ["lunch", "dinner", "breakfast", "meal", "restaurant", "brunch", "supper", "tea", "cafe", "coffee", "food", "eat", "hawker", "makan", "dabao", "tapao", "zi char", "cai png", "kopitiam", "hawker centre", "teh tarik", "kopi", "teh", "coffee shop"],
    "💪": ["gym", "workout", "run", "exercise", "training", "physio", "swim", "cycle", "yoga", "pilates", "#fit", "#fitness", "#workout", "#training", "virgin active", "ActiveSG", "bodypump", "GRID training", "boxing", "barre", "lift", "reformer"],
    "⚕️": ["doctor", "dentist", "appointment", "clinic", "hospital", "checkup", "therapy", "med", "medical", "vaccine", "physio", "poly", "polyclinic", "TCM", "sinseh"],
    "🎂": ["birthday", "bday", "anniversary", "celebration", "party", "cake"],
    "🫡": ["volunteer", "SAFVC"],
    "✝️": ["mass", "church", "prayer", "bible", "worship", "religion", "rite 1", "rite 2", "choir practice", "choir rehearsal"],
    "❤️": ["date night", "ES", "date", "romantic", "anniversary", "valentine", "#fun", "#datenight", "#XXX", "#love", "SS"],
    "🎉": ["party", "celebration", "festival", "gathering", "event", "ceremony", "wedding", "reunion", "farewell", "shindig"],
    "🏖️": ["vacation", "holiday", "beach", "trip", "getaway", "resort"],
    "🏠": ["home", "house", "family", "chores", "cleaning", "maintenance", "domestic"],
    "🛒": ["shopping", "groceries", "market", "store", "supermarket", "mall", "pasar", "provision shop", "mama shop", "NTUC", "Giant", "Cold Storage"],
    "🧑‍💻": ["work", "project", "deadline", "coding", "development", "deploy", "release", "review", "sprint", "office", "standup", "retro", "#adm", "admin", "administration", "1:1", "townhall", "all hands", "skip level", "one-on-one"],
    "📚": ["study", "class", "lecture", "exam", "test", "school", "university", "course", "assignment", "reading", "homework", "revision"],
    "🎬": ["movie", "film", "cinema", "theater", "theatre", "show", "screening", "netflix", "disney", "hbo", "prime"],
    "🎵": ["concert", "music", "gig", "recital", "performance", "band", "orchestra", "song", "opera"],
    "⚽": ["soccer", "tennis", "league", "sports", "golf", "baseball", "volleyball", "hockey", "run", "marathon", "RMCF", "Real Madrid"],
    "🧘": ["meditate", "mindfulness", "relax", "wellness", "spa", "retreat"],
    "🚗": ["car", "drive", "roadtrip", "service", "mechanic", "vehicle", "uber", "lyft", "taxi", "grab", "gojek", "comfort delgro", "SBS", "SMRT"],
    "🌪️": ["iowa state university", "isu", "mbb", "wbb", "fb", "basketball," "football"],
    "💯": ["interview", "job", "#job", "career", "application", "offer", "resume", "headhunt"],
    "🩺": ["health", "doctor", "checkup", "clinic", "hospital", "appointment", "test", "scan", "medical", "vaccine"],
    "🛏️": ["sleep", "nap", "rest", "bedtime", "zzz", "asleep", "haircut"],
    "🍼": ["baby", "feeding", "diaper", "infant", "toddler", "childcare" "kid", "#KID", "child", "gynie"],
    "🔥": ["#mou"],  # Added for #MOU
    "🚲": ["bike", "bicycle", "cycle", "ebike", "e-bike", "cycling", "biking",],  # Added for cycling
    "🐈": ["pet", "vet", "veterinarian," "cat", "kitten", "🐈", "focus", "Dewey" "DW Cat" "Dewey Wellington" "Wellington"],  # Added for focus/cat
    "⚠️": ["hold", "#fuc"],  # Added for HOLD and #FUC items
    "🗓️": ["event", "reminder", "note", "todo", "task", "plan", "schedule"],  # fallback
}

def get_event_icon(summary: str) -> str:
    """Returns an emoji icon based on keywords in the event summary."""
    lower_summary = summary.lower()
    for icon, keywords in EVENT_ICON_KEYWORDS.items():
        if any(keyword in lower_summary for keyword in keywords):
            return icon
    return "🗓️"

def fetch_and_process_calendars() -> str:
    """Fetches all ICS calendar feeds and returns properly merged ICS data as string."""
    logging.info("   -> Fetching .ics calendar feeds via Python only...")
    
    # Collect all events from all calendars
    all_events_components = []
    calendar_props = None
    
    for idx, url in enumerate(Config.ICAL_FEEDS):
        if "PASTE_YOUR" in url:
            logging.warning(f"   -> Skipping placeholder calendar URL at index {idx}")
            continue
        for attempt in range(Config.DOWNLOAD_RETRIES):
            try:
                r = requests.get(url, timeout=15)
                r.raise_for_status()
                
                # Parse this individual calendar
                try:
                    cal = icalendar.Calendar.from_ical(r.text)
                    # Store calendar properties from first calendar
                    if calendar_props is None:
                        calendar_props = cal
                    
                    # Extract all VEVENT components
                    for component in cal.walk():
                        if component.name == "VEVENT":
                            all_events_components.append(component)
                    
                    logging.info(f"   -> Downloaded calendar feed #{idx+1} with {len([c for c in cal.walk() if c.name == 'VEVENT'])} events")
                except Exception as e:
                    logging.warning(f"   -> Failed to parse calendar feed #{idx+1}: {e}")
                
                break
            except requests.RequestException as e:
                logging.warning(f"   -> Attempt {attempt+1} failed for calendar feed #{idx+1}: {e}")
                time.sleep(Config.DOWNLOAD_RETRY_DELAY_SECONDS)
    
    # Create a new merged calendar
    if calendar_props is None:
        # No valid calendars found, return empty calendar
        merged_cal = icalendar.Calendar()
        merged_cal.add('prodid', '-//Huang Di Dashboard//Dashboard Generator//EN')
        merged_cal.add('version', '2.0')
    else:
        # Use properties from first valid calendar
        merged_cal = icalendar.Calendar()
        for key, value in calendar_props.items():
            merged_cal.add(key, value)
    
    # Add all events to merged calendar
    for event_component in all_events_components:
        merged_cal.add_component(event_component)
    
    logging.info(f"   -> Merged {len(all_events_components)} total events from all calendars")
    return merged_cal.to_ical().decode('utf-8')

def parse_events(ical_data_str: str, timezone_str: str) -> List[Dict[str, Any]]:
    """Parse events from raw ICS data string with improved recurrence handling."""
    all_events = []
    try:
        cal = icalendar.Calendar.from_ical(ical_data_str)
        # Pass 1: Collect master events, overrides, and cancellations
        master_events = []
        overrides = {}
        cancelled_keys = set()
        debug_counter = 0  # Debug counter for RRULE logging
        for component in cal.walk():
            if component.name != "VEVENT":
                continue
            uid = str(component.get('UID', '') or '')
            recurrence_id = component.get('RECURRENCE-ID')
            status = str(component.get('STATUS', '') or '').upper()
            summary = str(component.get('SUMMARY', '') or '')
            description = str(component.get('DESCRIPTION', '') or '')
            transparency = str(component.get('TRANSP', '') or '').lower()
            cancelled = False
            if status == "CANCELLED":
                cancelled = True
            if "cancelled" in summary.lower() or "canceled" in summary.lower() or "cancelled" in description.lower() or "canceled" in description.lower():
                cancelled = True
            if transparency == "opaque" and not component.get('DTSTART'):
                cancelled = True
            if component.get('DTSTART') and component.get('DTEND'):
                dtstart = component.get('DTSTART').dt
                dtend = component.get('DTEND').dt
                if isinstance(dtstart, date) and not isinstance(dtstart, datetime):
                    if (dtend - dtstart).days > 1 and not summary:
                        cancelled = True
            if recurrence_id:
                # This is an override or exception
                if status == "CANCELLED" or not any([component.get('SUMMARY'), component.get('LOCATION'), component.get('DESCRIPTION')]):
                    cancelled = True
            key = (uid, recurrence_id.dt if recurrence_id and hasattr(recurrence_id, 'dt') else None)
            if cancelled:
                cancelled_keys.add(key)
                continue
            if recurrence_id:
                overrides[key] = component
            else:
                master_events.append(component)
        # Pass 2: Expand events (recurring, single, overrides)
        for event in master_events:
            uid = str(event.get('UID', '') or '')
            key = (uid, None)
            if key in cancelled_keys:
                continue
            rrule_val = event.get('RRULE')
            dtstart = event.get('DTSTART').dt if event.get('DTSTART') else None
            dtend = event.get('DTEND').dt if event.get('DTEND') else None
            
            # If no end time is specified, add a default duration (1 hour for timed events)
            if not dtend and dtstart:
                if isinstance(dtstart, date) and not isinstance(dtstart, datetime):
                    # All-day event, use same date
                    dtend = dtstart
                else:
                    # Timed event, add 1 hour duration
                    try:
                        dtend = dtstart + timedelta(hours=1)
                    except Exception:
                        dtend = dtstart
            exdates = []
            if event.get('EXDATE'):
                exdate_val = event.get('EXDATE')
                if isinstance(exdate_val, list):
                    for ex in exdate_val:
                        if hasattr(ex, 'dts'):
                            exdates.extend([d.dt for d in ex.dts])
                        elif hasattr(ex, 'dt'):
                            exdates.append(ex.dt)
                else:
                    if hasattr(exdate_val, 'dts'):
                        exdates.extend([d.dt for d in exdate_val.dts])
                    elif hasattr(exdate_val, 'dt'):
                        exdates.append(exdate_val.dt)
            if rrule_val and dtstart:
                # Expand recurring events
                try:
                    # Get the raw RRULE string
                    rrule_str = icalendar.prop.vRecur.to_ical(rrule_val).decode()
                    
                    # For rrulestr parsing, we need to use naive datetimes consistently
                    # Convert dtstart to naive datetime in the local timezone
                    if isinstance(dtstart, datetime) and dtstart.tzinfo is not None:
                        # Use Arrow to convert to local timezone, then make naive
                        dtstart_arrow = arrow.get(dtstart).to(timezone_str)
                        rule_dtstart = dtstart_arrow.naive
                        
                        # Also convert UNTIL to naive format to match the naive dtstart
                        if "UNTIL=" in rrule_str and rrule_str.find("UNTIL=") != -1:
                            rrule_str = convert_rrule_until_to_naive(rrule_str, timezone_str)
                    elif isinstance(dtstart, date) and not isinstance(dtstart, datetime):
                        # Convert date to datetime for rrule
                        rule_dtstart = datetime.combine(dtstart, datetime.min.time())
                    else:
                        rule_dtstart = dtstart
                    
                    # Debug: Log the original RRULE for the first few events
                    if debug_counter < 3:  # Only log first 3 to avoid spam
                        logging.info(f"Debug: Trying rrulestr with naive dtstart for {uid}")
                        logging.info(f"Debug: RRULE: {rrule_str}")
                        logging.info(f"Debug: rule_dtstart: {rule_dtstart} (naive: {rule_dtstart.tzinfo is None if hasattr(rule_dtstart, 'tzinfo') else 'N/A'})")
                        debug_counter += 1
                    
                    rule = rrulestr(rrule_str, dtstart=rule_dtstart)
                except Exception as e:
                    logging.warning(f"Failed to parse RRULE for event {uid}: {e}")
                    continue
                
                # Create timezone-consistent window for expansion
                window_start = arrow.now(timezone_str).floor('day').datetime
                window_end = window_start + timedelta(days=2)
                
                # Normalize window times to match rule dtstart timezone awareness
                if isinstance(dtstart, datetime) and dtstart.tzinfo is not None:
                    # Since we used naive local time for rrule, the window should also be naive local time
                    window_start_naive = arrow.get(window_start).to(timezone_str).naive
                    window_end_naive = arrow.get(window_end).to(timezone_str).naive
                    try:
                        occurrences_naive = list(rule.between(window_start_naive, window_end_naive, inc=True))
                        # Convert back to timezone-aware in the original timezone
                        occurrences = []
                        for occ_naive in occurrences_naive:
                            # The occurrence is in local timezone, add timezone info and convert to original timezone
                            occ_local_aware = arrow.get(occ_naive, timezone_str).datetime
                            if dtstart.tzinfo:
                                occ_final = occ_local_aware.astimezone(dtstart.tzinfo)
                            else:
                                occ_final = occ_local_aware
                            occurrences.append(occ_final)
                    except Exception as e:
                        logging.warning(f"Failed to expand recurrences for event {uid}: {e}")
                        occurrences = []
                elif isinstance(dtstart, date) and not isinstance(dtstart, datetime):
                    # All-day event - work with dates
                    window_start_date = window_start.date()
                    window_end_date = window_end.date()
                    try:
                        occurrences_dt = list(rule.between(
                            datetime.combine(window_start_date, datetime.min.time()),
                            datetime.combine(window_end_date, datetime.min.time()),
                            inc=True
                        ))
                        # Convert back to dates for all-day events
                        occurrences = [occ.date() for occ in occurrences_dt]
                    except Exception as e:
                        logging.warning(f"Failed to expand recurrences for event {uid}: {e}")
                        occurrences = []
                else:
                    # Timezone-naive datetime
                    try:
                        # Convert window to naive datetimes
                        window_start_naive = window_start.replace(tzinfo=None) if window_start.tzinfo else window_start
                        window_end_naive = window_end.replace(tzinfo=None) if window_end.tzinfo else window_end
                        occurrences = list(rule.between(window_start_naive, window_end_naive, inc=True))
                    except Exception as e:
                        logging.warning(f"Failed to expand recurrences for event {uid}: {e}")
                        occurrences = []
                for occ in occurrences:
                    occ_key = (uid, occ)
                    if occ in exdates or occ_key in cancelled_keys:
                        continue
                    # Use override if present
                    if occ_key in overrides:
                        comp = overrides[occ_key]
                        dtstart_inst = comp.get('DTSTART').dt if comp.get('DTSTART') else occ
                        dtend_inst = comp.get('DTEND').dt if comp.get('DTEND') else dtstart_inst
                        summary = str(comp.get('SUMMARY', '') or '')
                        description = str(comp.get('DESCRIPTION', '') or '')
                        location = str(comp.get('LOCATION', '') or '')
                    else:
                        dtstart_inst = occ
                        # Calculate duration safely, handling type mismatches
                        duration = timedelta(hours=1)  # Default duration
                        if dtend and dtstart:
                            try:
                                # Ensure both are the same type for proper duration calculation
                                if isinstance(dtstart, datetime) and isinstance(dtend, datetime):
                                    duration = dtend - dtstart
                                elif isinstance(dtstart, date) and isinstance(dtend, date) and not isinstance(dtstart, datetime) and not isinstance(dtend, datetime):
                                    duration = dtend - dtstart
                                # If types don't match, use default duration
                            except Exception:
                                # Fall back to default duration on any calculation error
                                duration = timedelta(hours=1)
                        dtend_inst = dtstart_inst + duration
                        summary = str(event.get('SUMMARY', '') or '')
                        description = str(event.get('DESCRIPTION', '') or '')
                        location = str(event.get('LOCATION', '') or '')
                    all_day = isinstance(dtstart_inst, date) and not isinstance(dtstart_inst, datetime)
                    try:
                        begin_local = arrow.get(dtstart_inst).to(timezone_str)
                        end_local = arrow.get(dtend_inst).to(timezone_str)
                    except Exception:
                        begin_local = dtstart_inst
                        end_local = dtend_inst
                    all_events.append({
                        'uid': uid,
                        'summary': summary,
                        'description': description,
                        'location': location,
                        'begin_local': begin_local,
                        'end_local': end_local,
                        'all_day': all_day,
                        'cal_name': None,
                        'is_recurring': True
                    })
            elif dtstart:
                # Single event
                all_day = isinstance(dtstart, date) and not isinstance(dtstart, datetime)
                try:
                    begin_local = arrow.get(dtstart).to(timezone_str)
                    end_local = arrow.get(dtend).to(timezone_str) if dtend else begin_local
                except Exception:
                    begin_local = dtstart
                    end_local = dtend
                all_events.append({
                    'uid': uid,
                    'summary': str(event.get('SUMMARY', '') or ''),
                    'description': str(event.get('DESCRIPTION', '') or ''),
                    'location': str(event.get('LOCATION', '') or ''),
                    'begin_local': begin_local,
                    'end_local': end_local,
                    'all_day': all_day,
                    'cal_name': None,
                    'is_recurring': False
                })
    except Exception as e:
        logging.warning(f"Error in parse_events: {e}", exc_info=True)
    return all_events

def expand_recurring_events(component, timezone_str, exceptions):
    """Expand a recurring event into individual instances with exception handling."""
    expanded_events = []
    uid = str(component.get('uid', ''))
    summary = str(component.get('summary', ''))
    description = str(component.get('description', ''))
    location = str(component.get('location', ''))
    
    # Get start and end in local timezone
    start = convert_to_local(component.get('dtstart').dt, timezone_str)
    end = convert_to_local(component.get('dtend').dt if component.get('dtend') else component.get('dtstart').dt, timezone_str)
    
    # All-day event detection
    all_day = isinstance(start, date) and not isinstance(start, datetime)
    
    # Parse recurrence rule
    rrule_dict = component.get('rrule')
    if not rrule_dict:
        return expanded_events
        
    freq = rrule_dict.get('FREQ', ['DAILY'])[0]
    interval = int(rrule_dict.get('INTERVAL', [1])[0])
    count = int(rrule_dict.get('COUNT', [0])[0]) if 'COUNT' in rrule_dict else 0
    
    # Handle UNTIL
    until = None
    if 'UNTIL' in rrule_dict:
        until_val = rrule_dict.get('UNTIL')[0]
        if isinstance(until_val, datetime):
            until = convert_to_local(until_val, timezone_str)
        else:
            until = until_val
    
    # Get excluded dates
    exdates = []
    if 'EXDATE' in component:
        for exdate in component.get('EXDATE', []):
            if isinstance(exdate, list):
                for ex in exdate:
                    local_ex = convert_to_local(getattr(ex, 'dt', None), timezone_str)
                    if isinstance(local_ex, datetime):
                        exdates.append(local_ex.date())
                    elif isinstance(local_ex, date):
                        exdates.append(local_ex)
            else:
                local_ex = convert_to_local(getattr(exdate, 'dt', None), timezone_str)
                if isinstance(local_ex, datetime):
                    exdates.append(local_ex.date())
                elif isinstance(local_ex, date):
                    exdates.append(local_ex)
    
    # Calculate recurrence dates based on frequency
    recurrence_dates = []
    
    # Determine how many dates to generate
    if count > 0:
        max_instances = count
    else:
        # Set reasonable limits based on frequency
        if freq == 'DAILY':
            max_instances = 365  # About a year
        elif freq == 'WEEKLY':
            max_instances = 52*2  # Two years
        elif freq == 'MONTHLY':
            max_instances = 24  # Two years
        elif freq == 'YEARLY':
            max_instances = 5
        else:
            max_instances = 10  # Default for unknown frequency
    
    # Generate recurrence dates
    current_date = start
    instances_generated = 0
    
    while instances_generated < max_instances:
        # Defensive: skip if current_date is None
        if not current_date:
            break
        # Check if we've reached UNTIL date
        if until and hasattr(current_date, 'date') and hasattr(until, 'date'):
            # Defensive: .date() only for datetime, not date
            if isinstance(current_date, datetime) and isinstance(until, datetime):
                if current_date.date() > until.date():
                    break
            elif isinstance(current_date, date) and isinstance(until, date):
                if current_date > until:
                    break
        # Defensive: get event_date
        if isinstance(current_date, datetime):
            event_date = current_date.date()
        else:
            event_date = current_date
        # Check if date is excluded
        if event_date not in exdates:
            # Check if there's a modified exception for this instance
            if event_date in exceptions:
                # Use the modified event
                modified_component = exceptions[event_date]
                modified_event = process_single_event(modified_component, None, timezone_str)
                if modified_event:
                    expanded_events.append(modified_event)
            else:
                # Generate regular instance
                duration = timedelta(hours=1)  # Default duration
                if start is not None and end is not None:
                    # Calculate duration from original event
                    try:
                        if isinstance(start, datetime) and isinstance(end, datetime):
                            duration = end - start
                        elif isinstance(start, date) and isinstance(end, date) and not isinstance(start, datetime) and not isinstance(end, datetime):
                            duration = end - start
                        else:
                            # Mixed types - convert to datetime for calculation
                            if isinstance(start, date) and not isinstance(start, datetime):
                                start_dt = datetime.combine(start, datetime.min.time())
                            else:
                                start_dt = start
                            if isinstance(end, date) and not isinstance(end, datetime):
                                end_dt = datetime.combine(end, datetime.min.time())
                            else:
                                end_dt = end
                            if isinstance(start_dt, datetime) and isinstance(end_dt, datetime):
                                duration = end_dt - start_dt
                    except Exception:
                        duration = timedelta(hours=1)
                try:
                    instance_end = current_date + duration
                except Exception:
                    instance_end = current_date
                event = {
                    'uid': f"{uid}-{event_date}",
                    'summary': summary,
                    'description': description,
                    'location': location,
                    'begin_local': current_date,
                    'end_local': instance_end,
                    'all_day': all_day,
                    'cal_name': None,  # Will be set by process_single_event
                    'is_recurring': True
                }
                expanded_events.append(event)
        # Increment to next occurrence based on frequency
        try:
            if freq == 'DAILY':
                current_date += timedelta(days=interval)
            elif freq == 'WEEKLY':
                current_date += timedelta(weeks=interval)
            elif freq == 'MONTHLY':
                # Get same day next month (handling month length differences)
                month = getattr(current_date, 'month', 1) - 1 + interval
                year = getattr(current_date, 'year', 1) + month // 12
                month = month % 12 + 1
                day = min(getattr(current_date, 'day', 1), calendar.monthrange(year, month)[1])
                if isinstance(current_date, datetime):
                    current_date = current_date.replace(year=year, month=month, day=day)
                else:
                    current_date = date(year, month, day)
            elif freq == 'YEARLY':
                if isinstance(current_date, datetime):
                    current_date = current_date.replace(year=current_date.year + interval)
                else:
                    current_date = date(getattr(current_date, 'year', 1) + interval,
                                        getattr(current_date, 'month', 1),
                                        getattr(current_date, 'day', 1))
        except Exception:
            break
        instances_generated += 1
    
    return expanded_events

def process_single_event(component, cal_name, timezone_str):
    """Process a single event component."""
    uid = str(component.get('uid', ''))
    summary = str(component.get('summary', ''))
    description = str(component.get('description', ''))
    location = str(component.get('location', ''))
    
    # Check for cancelled status
    status = str(component.get('status', ''))
    if status.upper() == 'CANCELLED':
        return None
    
    # Get start and end times
    start = component.get('dtstart')
    if not start:
        return None
        
    end = component.get('dtend')
    has_explicit_end = end is not None
    if not end:
        end = start
    
    # Convert to local timezone
    start_local = convert_to_local(start.dt, timezone_str)
    end_local = convert_to_local(end.dt, timezone_str)
    
    # Detect all-day event
    all_day = isinstance(start.dt, date) and not isinstance(start.dt, datetime)
    
    # Handle default duration for timed events without explicit end times
    if not has_explicit_end and not all_day and isinstance(start_local, datetime):
        # Add 1 hour default duration for timed events without explicit end time
        end_local = start_local + timedelta(hours=1)
    
    # Handle all-day events that end at midnight
    if all_day and isinstance(end_local, date):
        # iCalendar spec: all-day events' end date is exclusive
        # Adjust to make the end date inclusive by subtracting one day
        end_local = end_local - timedelta(days=1)
    
    event = {
        'uid': uid,
        'summary': summary,
        'description': description,
        'location': location,
        'begin_local': start_local,
        'end_local': end_local,
        'all_day': all_day,
        'cal_name': cal_name,
        'is_recurring': False
    }
    
    return event

def convert_to_local(dt, timezone_str):
    """Convert a date or datetime to the local timezone."""
    if not dt:
        return None
        
    # If it's just a date, not a datetime, return as is
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return dt
        
    # If it's a datetime with no timezone, assume it's already local
    if not hasattr(dt, 'tzinfo') or dt.tzinfo is None:
        return dt
        
    # Convert to the specified timezone
    local_tz = pytz.timezone(timezone_str)
    return dt.astimezone(local_tz)

# ==============================================================================
# PDF GENERATION & UPLOAD
# ==============================================================================

def create_cover_page_pdf(temp_path: Path) -> Optional[Path]:
    """Creates a cover page PDF from configurable cover image path or defaults, scaled to reMarkable 2 dimensions."""
    # Check for configurable cover image path first
    cover_image_path = None
    image_format = "unknown"
    
    if Config.COVER_IMAGE_PATH and Config.COVER_IMAGE_PATH.exists():
        cover_image_path = Config.COVER_IMAGE_PATH
        if cover_image_path.suffix.lower() in ['.jpg', '.jpeg']:
            image_format = "JPG"
        elif cover_image_path.suffix.lower() == '.png':
            image_format = "PNG"
        else:
            image_format = cover_image_path.suffix.upper()
    else:
        # Fall back to default locations
        cover_image_jpg = Config.BASE_DIR / "cover-image.jpg"
        cover_image_png = Config.BASE_DIR / "cover-image.png"
        
        if cover_image_jpg.exists():
            cover_image_path = cover_image_jpg
            image_format = "JPG"
        elif cover_image_png.exists():
            cover_image_path = cover_image_png
            image_format = "PNG"
    
    if not cover_image_path:
        logging.info("   -> No cover image found, skipping cover page.")
        return None
    
    logging.info(f"   -> Creating cover page from {cover_image_path.name} ({image_format}) scaled for reMarkable 2...")
    cover_pdf_path = temp_path / "cover.pdf"
    
    # Create HTML with the cover image, sized for reMarkable 2 dimensions (1404x1872 px ≈ 5.3"x7.0")
    cover_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            @page {{
                size: 5.3in 7.0in;
                margin: 0;
            }}
            body {{
                margin: 0;
                padding: 0;
                width: 5.3in;
                height: 7.0in;
                display: flex;
                justify-content: center;
                align-items: center;
                background: white;
                overflow: hidden;
            }}
            .cover-image {{
                max-width: 5.3in;
                max-height: 7.0in;
                width: auto;
                height: auto;
                object-fit: contain;
            }}
        </style>
    </head>
    <body>
        <img src="file:///{cover_image_path.as_posix()}" class="cover-image" alt="Cover Image" />
    </body>
    </html>
    """
    
    try:
        html = HTML(string=cover_html, base_url=str(Config.BASE_DIR))
        html.write_pdf(cover_pdf_path)
        
        if cover_pdf_path.exists() and cover_pdf_path.stat().st_size > 1024:
            logging.info(f"   -> Cover page created successfully: {cover_pdf_path}")
            return cover_pdf_path
        else:
            logging.warning("   -> Cover page PDF generation failed or resulted in empty file")
            return None
    except Exception as e:
        logging.error(f"   -> Error creating cover page: {e}")
        return None

def merge_pdfs(cover_pdf: Path, main_pdf: Path, output_pdf: Path) -> bool:
    """Merges cover page and main PDF into final output."""
    try:
        logging.info("   -> Merging cover page with main dashboard PDF...")
        writer = PdfWriter()
        
        # Add cover page
        with open(cover_pdf, 'rb') as cover_file:
            cover_reader = PdfReader(cover_file)
            for page in cover_reader.pages:
                writer.add_page(page)
        
        # Add main content
        with open(main_pdf, 'rb') as main_file:
            main_reader = PdfReader(main_file)
            for page in main_reader.pages:
                writer.add_page(page)
        
        # Write merged PDF
        with open(output_pdf, 'wb') as output_file:
            writer.write(output_file)
        
        if output_pdf.exists() and output_pdf.stat().st_size > 1024:
            logging.info(f"   -> PDF merge completed successfully: {output_pdf}")
            return True
        else:
            logging.error("   -> PDF merge failed or resulted in empty file")
            return False
            
    except Exception as e:
        logging.error(f"   -> Error merging PDFs: {e}")
        return False

def generate_multipage_pdf(contexts: List[Dict[str, Any]], temp_path: Path) -> Path:
    """Renders HTML from template and converts to PDF using WeasyPrint, with robust error handling."""
    main_pdf_file = temp_path / "dashboard_main.pdf"
    final_pdf_file = temp_path / "dashboard.pdf"
    
    try:
        # Validate and sanitize contexts before template rendering
        sanitized_contexts = _validate_and_sanitize_contexts(contexts)
        
        # Attempt template rendering with full error context preservation
        rendered_html = _render_template_with_fallback(sanitized_contexts, temp_path)
        
        # Inject style to make epigraph smaller so it fits on one line
        style_block = (
            "<style>"
            ".epigraph { font-size: 95% !important; }"
            "</style>"
        )
        # Insert style after <head> if present, else at the top
        if "<head>" in rendered_html:
            rendered_html = rendered_html.replace("<head>", "<head>" + style_block, 1)
        else:
            rendered_html = style_block + rendered_html
        
        (temp_path / "dashboard.html").write_text(rendered_html, encoding="utf-8")
        logging.info("   -> Converting HTML to PDF via WeasyPrint API (no zoom/DPI)...")
        html = HTML(string=rendered_html, base_url=Config.BASE_DIR)
        html.write_pdf(main_pdf_file)
        
        if not main_pdf_file.is_file() or main_pdf_file.stat().st_size < 1024:
            raise RuntimeError(f"Generated main PDF '{main_pdf_file}' is missing or appears to be empty. Aborting.")
        
        # Try to create and merge cover page
        cover_pdf = create_cover_page_pdf(temp_path)
        if cover_pdf:
            try:
                if merge_pdfs(cover_pdf, main_pdf_file, final_pdf_file):
                    logging.info("   -> Successfully created PDF with cover page.")
                    return final_pdf_file
                else:
                    logging.warning("   -> Cover page merge failed, using main PDF without cover.")
            except Exception as e:
                logging.warning(f"   -> Cover page merge failed with error: {e}, using main PDF without cover.")
        
        # If no cover page or merge failed, use main PDF as final
        if main_pdf_file.resolve() != final_pdf_file.resolve():
            shutil.copy(main_pdf_file, final_pdf_file)
        else:
            # If paths are the same, rename main to final
            main_pdf_file.rename(final_pdf_file)
        
        logging.info("   -> PDF generation completed (without cover page).")
        return final_pdf_file
        
    except Exception as pdf_error:
        logging.critical(f"❌ Critical PDF generation failure: {pdf_error}")
        logging.critical("   -> This error occurred despite template fallbacks")
        
        # Even PDF generation failed - this is a critical system error
        # Still try to save error information for debugging
        try:
            error_html = f'''<!DOCTYPE html>
<html><head><title>Critical Error</title></head>
<body>
<h1>❌ Critical System Error</h1>
<p>PDF generation failed completely.</p>
<p>Error: {str(pdf_error)}</p>
<p>Check system logs immediately.</p>
</body></html>'''
            
            error_file = temp_path / "critical_error.html"
            error_file.write_text(error_html, encoding="utf-8")
            logging.critical(f"   -> Error details saved to: {error_file}")
        except:
            pass  # If even error logging fails, give up gracefully
            
        # Re-raise the original error for upstream handling
        raise
    if main_pdf_file.resolve() != final_pdf_file.resolve():
        shutil.copy(main_pdf_file, final_pdf_file)
    else:
        # If paths are the same, rename main to final
        main_pdf_file.rename(final_pdf_file)
    
    logging.info("   -> PDF generation completed (without cover page).")
    return final_pdf_file

def check_remarkable_availability() -> str:
    """Checks if the reMarkable is reachable on the SSH port. Returns the working IP."""
    logging.info(f"   -> Pinging reMarkable at preferred IPs: {Config.REMARKABLE_IPS} ...")
    for ip in Config.REMARKABLE_IPS:
        try:
            with socket.create_connection((ip, 22), timeout=5):
                logging.info(f"   -> Connection successful to {ip}.")
                return ip
        except (socket.timeout, socket.error) as e:
            logging.warning(f"   -> reMarkable not reachable at {ip}:22. Error: {e}")
    logging.critical(f"reMarkable is not reachable at any known IPs: {Config.REMARKABLE_IPS}")
    raise ConnectionError(f"Could not connect to reMarkable at any known IPs: {Config.REMARKABLE_IPS}")

def upload_to_remarkable(pdf_path: Path, temp_path: Path, page_count: int, base_name: str, visible_name: str) -> None:
    """Uploads PDF and metadata to reMarkable, restarts UI, with failover."""
    logging.info("   -> Pushing to reMarkable and restarting...")
    try:
        # Use the provided visible_name for metadata
        if not visible_name:
            # fallback to base_name if not provided
            visible_name = base_name
        import uuid as _uuid
        doc_uuid = str(_uuid.uuid4())
        final_pdf_name = f"{doc_uuid}.pdf"
        final_metadata_name = f"{doc_uuid}.metadata"
        final_content_name = f"{doc_uuid}.content"
        metadata = {
            "deleted": False,
            "lastModified": str(arrow.now().int_timestamp * 1000),
            "metadatamodified": False,
            "modified": False,
            "parent": "",
            "pinned": True,
            "synced": True,
            "type": "DocumentType",
            "version": 1,
            "visibleName": visible_name
        }
        content = {
            "extraMetadata": {},
            "fileType": "pdf",
            "fontName": "",
            "lastOpenedPage": 0,
            "lineHeight": -1,
            "margins": 100,
            "pageCount": page_count,
            "textScale": 1,
            "transform": {}
        }
        (temp_path / final_metadata_name).write_text(json.dumps(metadata, indent=None))
        (temp_path / final_content_name).write_text(json.dumps(content, indent=None))
        dst_path = temp_path / final_pdf_name
        if pdf_path.resolve() != dst_path.resolve():
            shutil.copy(pdf_path, dst_path)
        else:
            # If already correct name, just ensure it's present
            pass
        remote_path = "/home/root/.local/share/remarkable/xochitl/"
        files_to_upload = [
            str(temp_path / final_pdf_name),
            str(temp_path / final_metadata_name),
            str(temp_path / final_content_name)
        ]
        last_error = None
        for ip in Config.REMARKABLE_IPS:
            try:
                run_command(
                    ["scp", "-i", str(Config.REMARKABLE_SSH_KEY), *files_to_upload,
                     f"{Config.REMARKABLE_USER}@{ip}:{remote_path}"],
                    timeout=Config.REMOTE_COMMAND_TIMEOUT_SECONDS
                )
                run_command(
                    ["ssh", "-i", str(Config.REMARKABLE_SSH_KEY), f"{Config.REMARKABLE_USER}@{ip}",
                     "systemctl restart xochitl"],
                    timeout=Config.REMOTE_COMMAND_TIMEOUT_SECONDS
                )
                logging.info(f"   -> Upload and restart successful to {ip}.")
                return
            except Exception as e:
                logging.error(f"   -> Upload/restart failed for {ip}: {e}", exc_info=True)
                last_error = e
        if last_error:
            logging.critical(f"Failed to upload to reMarkable at any known IPs: {Config.REMARKABLE_IPS}")
            raise ConnectionError(f"Could not upload to reMarkable at any known IPs: {Config.REMARKABLE_IPS}") from last_error
        logging.critical("Upload to reMarkable failed for unknown reasons, but no exception was caught.")
        raise RuntimeError("Upload to reMarkable failed for unknown reasons.")
    except Exception as e:
        logging.critical(f"Exception in upload_to_remarkable: {e}", exc_info=True)
        raise

# ==============================================================================
# DATA FETCHING
# ==============================================================================
def fetch_all_data() -> Dict[str, Any]:
    """Fetches all external data and handles failures gracefully."""
    logging.info("📡 Step 2/3: Fetching all data sources sequentially...")
    try:
        ics_data = fetch_and_process_calendars()
    except Exception as e:
        logging.error(f"The calendar fetching task failed: {e}", exc_info=True)
        ics_data = ""
    try:
        weather = get_weather_data()
    except Exception as e:
        logging.error(f"The weather fetching task failed: {e}", exc_info=True)
        weather = {}
    return {
        "ics_data": ics_data,
        "weather": weather,
    }

# ==============================================================================
# MAIN ORCHESTRATOR
# ==============================================================================
def build_page_context(i: int, page_data: Dict[str, Any], now: arrow.Arrow, total_pages: int,
                      has_today_events: bool, has_tomorrow_events: bool, has_today_tasks: bool, has_tomorrow_tasks: bool, weather_data_for_template: list, first_tomorrow_page_idx: Optional[int] = None, all_today_events: Optional[List[Dict[str, Any]]] = None, all_tomorrow_events: Optional[List[Dict[str, Any]]] = None, all_today_tasks: Optional[List[str]] = None, all_tomorrow_tasks: Optional[List[str]] = None) -> dict:
    """Helper to build the context for each dashboard page."""
    # Header and visibleName formatting
    weekday = now.format('dddd')
    day = now.format('D')
    month = now.format('MMMM')
    month_short = now.format('MMM')
    year = now.format('YYYY')
    year_short = now.format('YY')
    # For filename: NMS_W_2025_07_02[a]
    day_initials = ['M', 'T', 'W', 'R', 'F', 'Sa', 'Su']
    weekday_idx = now.weekday()  # Monday=0
    day_initial = day_initials[weekday_idx]
    pdf_filename_str = f"NMS_{day_initial}_{now.format('YYYY_MM_DD')}"
    # For visibleName: NMS_2_Jul_25
    visible_name_str = f"NMS_{day}_{month_short}_{year_short}"
    # For header: NMS: Wednesday, 2 July 2025
    today_header_str = f"NMS: {weekday}, {day} {month} {year}"
    # For tomorrow header: AMP: Thursday, 3 July 2025
    tomorrow = now.shift(days=1)
    tomorrow_header_str = f"AMP: {tomorrow.format('dddd')}, {tomorrow.format('D')} {tomorrow.format('MMMM')} {tomorrow.format('YYYY')}"

    # Determine if this is the first page for today or tomorrow
    # We'll set epigraph/weather only on the first page of each day's events
    show_epigraph = False
    show_weather = False
    epigraph = {'quote': '', 'author': ''}
    
    # Get today and tomorrow lists for epigraph/weather logic
    # (Note: These are legacy for determining first page of each day's events)
    
    # If this is the first today page (i == 0), show epigraph and weather
    if i == 0:
        show_epigraph = True
        show_weather = True
        epigraph = Config.EPIGRAPH if Config.EPIGRAPH else {'quote': '', 'author': ''}
    
    # If this is the first tomorrow page, show epigraph and weather
    if first_tomorrow_page_idx is not None and i == first_tomorrow_page_idx:
        show_epigraph = True
        show_weather = True
        epigraph = {'quote': 'They shall run and not be weary; they shall walk and not faint.', 'author': ''}

    # --- Robustly determine which day this page is for ---
    today_events_list = page_data.get('today_events', page_data.get('today', []))
    tomorrow_events_list = page_data.get('tomorrow_events', page_data.get('tomorrow', []))
    today_tasks_list = page_data.get('today_tasks', [])
    tomorrow_tasks_list = page_data.get('tomorrow_tasks', [])
    
    # If this page has any today content, it's a today page
    if (today_events_list and len(today_events_list) > 0) or (today_tasks_list and len(today_tasks_list) > 0):
        day = 'today'
    # If this page has any tomorrow content, it's a tomorrow page
    elif (tomorrow_events_list and len(tomorrow_events_list) > 0) or (tomorrow_tasks_list and len(tomorrow_tasks_list) > 0):
        day = 'tomorrow'
    # Fallback: determine by page index (before tomorrow section = today)
    elif first_tomorrow_page_idx is not None and i < first_tomorrow_page_idx:
        day = 'today'
    else:
        day = 'tomorrow'

    # --- Robustly determine if this is the first page for today or tomorrow ---
    is_first_today_page = (day == 'today' and i == 0)
    is_first_tomorrow_page = (day == 'tomorrow' and (first_tomorrow_page_idx is not None and i == first_tomorrow_page_idx))

    # --- Assign events and tasks for the correct day ---
    if day == 'today':
        # Use the pre-distributed events and tasks from page_data
        events = page_data.get('today_events', page_data.get('today', []))
        tasks = page_data.get('today_tasks', [])
    elif day == 'tomorrow':
        # Use the pre-distributed events and tasks from page_data
        events = page_data.get('tomorrow_events', page_data.get('tomorrow', []))
        tasks = page_data.get('tomorrow_tasks', [])
    else:
        events = []
        tasks = []

    # --- Add blank entries for handwriting (Option 4 Hybrid approach) ---
    blank_entries = []
    
    # 1. Blank entry after weather block (only on first page with weather)
    if show_weather:
        blank_entries.append(create_blank_entry("planning"))

    # 2. Strategic blank lines between events/tasks (processed by add_strategic_writing_spaces)
    # This will be handled later in the event/task processing

    # --- Determine overflow status for smart header display ---
    # Check if this is an overflow page (not the first page for this day's content AND there are items that span multiple pages)
    is_overflow_events_page = False
    is_overflow_tasks_page = False
    
    if day == 'today':
        # For today: check if we're past page 0, have events/tasks, AND there are multiple pages of today content
        if i > 0 and events and all_today_events and len(all_today_events) > Config.MAX_ITEMS_PER_PAGE:
            is_overflow_events_page = True
        if i > 0 and tasks and all_today_tasks and len(all_today_tasks) > 0:
            # Calculate how many today pages would have tasks
            today_pages_data = distribute_items_across_pages(all_today_events or [], all_today_tasks or [], Config.MAX_ITEMS_PER_PAGE)
            # Check if tasks appear on multiple pages
            pages_with_tasks = sum(1 for page in today_pages_data if page.get('tasks'))
            if pages_with_tasks > 1:
                is_overflow_tasks_page = True
    elif day == 'tomorrow':
        # For tomorrow: similar logic for tomorrow content
        if first_tomorrow_page_idx is not None and i > first_tomorrow_page_idx and events and all_tomorrow_events and len(all_tomorrow_events) > Config.MAX_ITEMS_PER_PAGE:
            is_overflow_events_page = True
        if first_tomorrow_page_idx is not None and i > first_tomorrow_page_idx and tasks and all_tomorrow_tasks and len(all_tomorrow_tasks) > 0:
            # Calculate how many tomorrow pages would have tasks
            tomorrow_pages_data = distribute_items_across_pages(all_tomorrow_events or [], all_tomorrow_tasks or [], Config.MAX_ITEMS_PER_PAGE)
            # Check if tasks appear on multiple pages
            pages_with_tasks = sum(1 for page in tomorrow_pages_data if page.get('tasks'))
            if pages_with_tasks > 1:
                is_overflow_tasks_page = True

    # --- Always set all required context fields ---
    context = {
        'events': events,
        'tasks': tasks,  # Use original tasks without notes section
        'blank_entries': blank_entries,
        'page_number': i + 1,
        'total_pages': total_pages,
        'last_updated_str': now.format('HH:mm ZZZ, dddd, MMMM D'),
        'has_today_events': has_today_events,
        'has_tomorrow_events': has_tomorrow_events,
        'has_today_tasks': has_today_tasks,
        'has_tomorrow_tasks': has_tomorrow_tasks,
        'today_date_str': now.format('dddd, MMMM D'),
        'epigraph': epigraph if show_epigraph else None,
        'weather_data': weather_data_for_template if show_weather else None,
        'today_header_str': today_header_str,
        'tomorrow_header_str': tomorrow_header_str,
        'visible_name_str': visible_name_str,
        'pdf_filename_str': pdf_filename_str,
        'day': day,
        'is_overflow_events_page': is_overflow_events_page,
        'is_overflow_tasks_page': is_overflow_tasks_page,
        'show_events_header': events and not is_overflow_events_page,
        'show_tasks_header': tasks and not is_overflow_tasks_page,  # Use original tasks
        'events_continuation_text': "Events continued from previous page" if is_overflow_events_page else "",
        'tasks_continuation_text': "Tasks continued from previous page" if is_overflow_tasks_page else "",
    }
    return context

def create_notes_page_context(day: str, now: arrow.Arrow, page_number: int, total_pages: int) -> Dict[str, Any]:
    """Creates a context for a notes page at the end of a day's section.
    
    Args:
        day: 'today' or 'tomorrow'
        now: Current time as Arrow object
        page_number: The page number for this notes page
        total_pages: Total number of pages in the document
    
    Returns:
        Context dictionary for the notes page
    """
    # Header formatting
    weekday = now.format('dddd')
    day_num = now.format('D')
    month = now.format('MMMM')
    month_short = now.format('MMM')
    year = now.format('YYYY')
    year_short = now.format('YY')
    
    # Day initials for filename
    day_initials = ['M', 'T', 'W', 'R', 'F', 'Sa', 'Su']
    weekday_idx = now.weekday()  # Monday=0
    day_initial = day_initials[weekday_idx]
    pdf_filename_str = f"NMS_{day_initial}_{now.format('YYYY_MM_DD')}"
    visible_name_str = f"NMS_{day_num}_{month_short}_{year_short}"
    
    if day == 'today':
        header_str = f"Notes: {weekday}, {day_num} {month} {year}"
    else:  # tomorrow
        tomorrow = now.shift(days=1)
        header_str = f"Notes: {tomorrow.format('dddd')}, {tomorrow.format('D')} {tomorrow.format('MMMM')} {tomorrow.format('YYYY')}"
    
    # Create multiple blank entries for a full notes page optimized for note-taking
    notes_entries = []
    for i in range(12):  # 12 blank lines for better note-taking coverage
        notes_entries.append(create_blank_entry("notes"))
    
    context = {
        'events': [],  # No events on notes page
        'tasks': [],   # No tasks on notes page  
        'blank_entries': notes_entries,  # Multiple blank entries for notes
        'page_number': page_number,
        'total_pages': total_pages,
        'last_updated_str': now.format('HH:mm ZZZ, dddd, MMMM D'),
        'has_today_events': False,
        'has_tomorrow_events': False,
        'has_today_tasks': False,
        'has_tomorrow_tasks': False,
        'today_date_str': now.format('dddd, MMMM D'),
        'epigraph': None,  # No epigraph on notes pages
        'weather_data': None,  # No weather on notes pages
        'today_header_str': header_str if day == 'today' else f"NMS: {weekday}, {day_num} {month} {year}",
        'tomorrow_header_str': header_str if day == 'tomorrow' else f"AMP: {now.shift(days=1).format('dddd')}, {now.shift(days=1).format('D')} {now.shift(days=1).format('MMMM')} {now.shift(days=1).format('YYYY')}",
        'visible_name_str': visible_name_str,
        'pdf_filename_str': pdf_filename_str,
        'day': day,
        'is_notes_page': True  # Flag to identify notes pages
    }
    return context

def validate_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Cleans and audits the event list before PDF generation.

    - Removes duplicate events (same summary, time, all-day status).
    - Removes events that appear to be cancelled (summary or description contains 'cancel').
    - Logs out-of-order events (but does not remove them).
    - Ensures all-day events are listed first for each day.
    - Removes all-day events that bleed into the next day (all-day events only appear on the day they start).
    - Logs all issues found and fixed to 'event_validation_log.txt'.

    Returns:
        A cleaned list of events, ready for further processing.
    """
    seen = set()
    last_day = None
    last_time = None
    issues = []
    fixed_events = []
    for i, event in enumerate(events):
        key = (event.get("summary"), str(event.get("begin_local")), str(event.get("end_local")), event.get("all_day"))
        duplicate = False
        out_of_order = False
        cancelled = False

        # Duplicate check
        if key in seen:
            issues.append(f"Duplicate event: {event.get('summary')} at {event.get('begin_local')}")
            duplicate = True
        else:
            seen.add(key)

        # Cancelled check (should not be present, but double check)
        summary_str = event.get("summary") or ""
        description_str = event.get("description") or ""
        if "cancel" in summary_str.lower() + description_str.lower():
            issues.append(f"Cancelled event present: {event.get('summary')} at {event.get('begin_local')}")
            cancelled = True

        # All-day bleed check: all-day events should only appear on the day they start
        if event.get("all_day"):
            begin_day = event["begin_local"].floor('day')
            end_day = event["end_local"].floor('day')
            if (end_day - begin_day).days > 1:
                issues.append(f"All-day event bleeding into next day: {event.get('summary')} from {event.get('begin_local')} to {event.get('end_local')}")
                cancelled = True  # Remove from output

        # Order check (per day)
        day = event["begin_local"].floor('day')
        if last_day is not None and day < last_day:
            issues.append(f"Out-of-order day: {event.get('summary')} at {event.get('begin_local')}")
            out_of_order = True
        if last_day == day and last_time is not None and event["begin_local"] < last_time:
            issues.append(f"Out-of-order time: {event.get('summary')} at {event.get('begin_local')}")
            out_of_order = True
        last_day = day
        last_time = event["begin_local"]

        # Only add event if not duplicate or cancelled
        if not duplicate and not cancelled:
            fixed_events.append(event)

    # --- Ensure all-day events are listed first for each day ---
    # Group by day
    events_by_day = {}
    for event in fixed_events:
        day = event["begin_local"].floor('day')
        events_by_day.setdefault(day, []).append(event)
    cleaned_events = []
    for day in sorted(events_by_day.keys()):
        day_events = events_by_day[day]
        all_day = [e for e in day_events if e.get("all_day")]
        timed = [e for e in day_events if not e.get("all_day")]
        all_day.sort(key=lambda e: (e["begin_local"], e["summary"]))
        timed.sort(key=lambda e: (e["begin_local"], e["summary"]))
        cleaned_events.extend(all_day + timed)

    # Write issues to a .txt file
    log_path = Path(Config.BASE_DIR) / "event_validation_log.txt"
    with open(log_path, "w", encoding="utf-8") as f:
        if issues:
            f.write("Event validation found issues and fixed them before PDF output:\n")
            for issue in issues:
                f.write(issue + "\n")
        else:
            f.write("Event validation: No issues found before PDF output.\n")
    if issues:
        logging.warning(f"Event validation found and fixed {len(issues)} issues. See {log_path}")
    else:
        logging.info("Event validation: No issues found before PDF output.")
    return cleaned_events

def process_events_for_template(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Process raw events into template-ready format with icons and display times."""
    processed_events = []
    
    for event in events:
        # Get the icon based on summary
        icon = get_event_icon(event.get('summary', ''))
        
        # Format display time
        begin_local = event.get('begin_local')
        end_local = event.get('end_local')
        
        if begin_local:
            if event.get('all_day'):
                display_time = "All day"
            else:
                try:
                    if hasattr(begin_local, 'format'):
                        start_time_str = begin_local.format('HH:mm')
                    else:
                        start_time_str = begin_local.strftime('%H:%M')
                    
                    # Check if we have a valid end time that's different from start time
                    if end_local and end_local != begin_local:
                        try:
                            if hasattr(end_local, 'format'):
                                end_time_str = end_local.format('HH:mm')
                            else:
                                end_time_str = end_local.strftime('%H:%M')
                            display_time = f"{start_time_str}-{end_time_str}"
                        except Exception:
                            # If end time formatting fails, just use start time
                            display_time = start_time_str
                    else:
                        # No valid end time or same as start time
                        display_time = start_time_str
                        
                except Exception:
                    display_time = "??:??"
        else:
            display_time = "??:??"
        
        # Create processed event
        processed_event = {
            'uid': event.get('uid', ''),
            'summary': event.get('summary', ''),
            'description': event.get('description', ''),
            'location': event.get('location', ''),
            'begin_local': begin_local,
            'end_local': event.get('end_local'),
            'all_day': event.get('all_day', False),
            'cal_name': event.get('cal_name'),
            'is_recurring': event.get('is_recurring', False),
            'icon': icon,
            'display_time': display_time
        }
        
        processed_events.append(processed_event)
    
    return processed_events

# ==============================================================================
# BLANK ENTRIES FOR HANDWRITING
# ==============================================================================
def add_strategic_writing_spaces(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Insert blank writing spaces after every 3 events for note-taking.
    
    Args:
        events: List of event dictionaries
    
    Returns:
        Enhanced events list with strategic blank entries for handwriting
    """
    if not events:
        return events
    
    enhanced_events = []
    for i, event in enumerate(events):
        enhanced_events.append(event)
        
        # Add blank writing space after every 3 events (but not after the last event)
        if (i + 1) % 3 == 0 and i < len(events) - 1:
            enhanced_events.append(create_blank_entry("notes"))
    
    return enhanced_events

def create_blank_entry(entry_type: str = "notes") -> Dict[str, Any]:
    """Creates a blank entry for handwriting on reMarkable.
    
    Args:
        entry_type: Type of blank entry ("notes", "planning", "tasks")
    
    Returns:
        Dict formatted like a regular event/task for template consistency
    """
    icons = {
        "notes": "✏️",
        "planning": "📝", 
        "tasks": "📋"
    }
    
    return {
        'uid': f'blank-{entry_type}-{arrow.now().timestamp}',
        'summary': '',  # Empty for handwriting
        'description': '',
        'location': '',
        'icon': icons.get(entry_type, "✏️"),
        'display_time': '',  # No time for blank entries
        'all_day': False,
        'is_blank_entry': True,  # Flag to identify blank entries
        'entry_type': entry_type
    }

# ==============================================================================
# AUTOMATION UTILITIES
# ==============================================================================

def diagnose_output_paths() -> None:
    """Diagnose and report on output path accessibility for troubleshooting."""
    logging.info("🔍 Diagnosing output path accessibility...")
    
    paths_to_check = [
        ("Configured LOCAL_OUTPUT_PATH", Config.LOCAL_OUTPUT_PATH),
        ("Script directory", Config.BASE_DIR),
        ("User Documents", Path.home() / "Documents" / "Huang_Di_Dashboard"),
        ("Current working directory", Path.cwd())
    ]
    
    for name, path in paths_to_check:
        if path:
            try:
                # Check if path exists or can be created
                path.mkdir(parents=True, exist_ok=True)
                
                # Test write access
                test_file = path / "access_test.tmp"
                test_file.write_text("Access test")
                test_file.unlink()
                
                logging.info(f"✅ {name}: {path} - ACCESSIBLE")
            except Exception as e:
                logging.warning(f"❌ {name}: {path} - NOT ACCESSIBLE: {e}")
        else:
            logging.info(f"⚠️ {name}: Not configured")

def detect_automation_mode() -> bool:
    """Detect if running in automation mode (scheduled task, cron, etc.)."""
    import sys
    
    # Check command line arguments
    if "--automation" in sys.argv or "--scheduled" in sys.argv:
        return True
    
    # Check environment variables
    if os.getenv("AUTOMATION_MODE", "").lower() in ("true", "1", "yes"):
        return True
    
    # Check if running without a terminal (common in scheduled tasks)
    try:
        if not sys.stdout.isatty():
            return True
    except (AttributeError, OSError):
        return True
    
    # Check for typical automation environment variables
    automation_indicators = [
        "GITHUB_ACTIONS", "CI", "BUILD_NUMBER", "JENKINS_URL",
        "TASK_NAME", "SCHEDULED_TASK", "CRON_JOB"
    ]
    
    if any(os.getenv(var) for var in automation_indicators):
        return True
    
    return False

def create_emergency_dashboard(now):
    """Create minimal emergency dashboard when all else fails."""
    logging.info("Creating emergency dashboard...")
    
    emergency_context = {
        'events': [],
        'tasks': [
            'Emergency Dashboard Generated',
            'Check system logs for errors',
            'Verify internet connectivity',
            'Check calendar feed URLs'
        ],
        'blank_entries': [create_blank_entry("notes") for _ in range(8)],
        'page_number': 1,
        'total_pages': 1,
        'last_updated_str': now.format('HH:mm ZZZ, dddd, MMMM D'),
        'day': 'today',
        'epigraph': {
            'quote': 'Emergency Dashboard - System encountered errors during generation',
            'author': 'Huang Di Dashboard Generator'
        },
        'weather_data': [{'location': '⚠️', 'narrative': 'Weather data unavailable due to system error'}],
        'today_header_str': f"EMERGENCY: {now.format('dddd, MMMM D, YYYY')}",
        'tomorrow_header_str': f"Tomorrow: {now.shift(days=1).format('dddd, MMMM D')}",
        'visible_name_str': f"EMERGENCY_{now.format('D_MMM_YY')}",
        'pdf_filename_str': f"EMERGENCY_{now.format('YYYY_MM_DD')}",
        'has_today_events': False,
        'has_tomorrow_events': False,
        'has_today_tasks': True,
        'has_tomorrow_tasks': False,
        'today_date_str': now.format('dddd, MMMM D'),
        'is_overflow_events_page': False,
        'is_overflow_tasks_page': False,
        'show_events_header': False,
        'show_tasks_header': True,
        'events_continuation_text': "",
        'tasks_continuation_text': "",
    }
    
    with tempfile.TemporaryDirectory() as temp_dir:
        emergency_name = f"EMERGENCY_{now.format('YYYY_MM_DD')}"
        pdf_path = generate_multipage_pdf([emergency_context], Path(temp_dir))
        
        # Save local copy with comprehensive fallback logic
        if Config.LOCAL_OUTPUT_PATH:
            try:
                Config.LOCAL_OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
                dest_path = Config.LOCAL_OUTPUT_PATH / f"{emergency_name}.pdf"
                shutil.copy(pdf_path, dest_path)
                logging.info(f"✅ Emergency dashboard saved to {dest_path}")
            except Exception as e:
                logging.error(f"Failed to save emergency dashboard to primary location: {e}")
                
                # Fallback 1: Script directory
                try:
                    fallback_path = Config.BASE_DIR / f"{emergency_name}.pdf"
                    shutil.copy(pdf_path, fallback_path)
                    logging.info(f"✅ Emergency dashboard saved to script directory: {fallback_path}")
                except Exception as fallback_e:
                    logging.error(f"Emergency dashboard fallback save failed: {fallback_e}")
                    
                    # Fallback 2: Documents folder
                    try:
                        docs_path = Path.home() / "Documents" / "Huang_Di_Dashboard"
                        docs_path.mkdir(parents=True, exist_ok=True)
                        final_path = docs_path / f"{emergency_name}.pdf"
                        shutil.copy(pdf_path, final_path)
                        logging.info(f"✅ Emergency dashboard saved to Documents: {final_path}")
                    except Exception as docs_e:
                        logging.critical(f"All emergency dashboard save attempts failed: {docs_e}")
        else:
            # No local output configured, save to script directory
            try:
                fallback_path = Config.BASE_DIR / f"{emergency_name}.pdf"
                shutil.copy(pdf_path, fallback_path)
                logging.info(f"✅ Emergency dashboard saved to script directory: {fallback_path}")
            except Exception as e:
                logging.critical(f"Emergency dashboard save failed: {e}")

# ==============================================================================
# DISTRIBUTE ITEMS ACROSS PAGES
# ==============================================================================
# Task checklists for each day
CHECKLIST_TODAY = [
    "Top 3 Things",
    "Devotions, SFAD, Journal", 
    "Meals & Expenses",
    "Pegboard Compline"
]

CHECKLIST_TOMORROW = [
    "Top 3 Things",
    "Plan for SAFVC",
    "Zero Strikes Virgin Active", 
    "All AMP Staged"
]

def validate_distribution_balance(pages: List[Dict[str, Any]], total_events: int, total_tasks: int, max_items: int) -> bool:
    """
    Validates that the distribution is properly balanced and meets quality standards.
    
    Args:
        pages: List of page dictionaries with 'events' and 'tasks' keys
        total_events: Original number of events
        total_tasks: Original number of tasks
        max_items: Maximum items per page
    
    Returns:
        True if distribution passes validation, False otherwise
    """
    import logging
    
    if not pages:
        return total_events == 0 and total_tasks == 0
    
    # Check 1: All items are preserved
    distributed_events = sum(len(page['events']) for page in pages)
    distributed_tasks = sum(len(page['tasks']) for page in pages)
    
    if distributed_events != total_events:
        logging.warning(f"❌ Distribution validation failed: Expected {total_events} events, got {distributed_events}")
        return False
    
    if distributed_tasks != total_tasks:
        logging.warning(f"❌ Distribution validation failed: Expected {total_tasks} tasks, got {distributed_tasks}")
        return False
    
    # Check 2: No page exceeds max_items
    for i, page in enumerate(pages):
        page_total = len(page['events']) + len(page['tasks'])
        if page_total > max_items:
            logging.warning(f"❌ Distribution validation failed: Page {i+1} has {page_total} items (max: {max_items})")
            return False
    
    # Check 3: Distribution balance (avoid severely uneven pages)
    page_totals = [len(page['events']) + len(page['tasks']) for page in pages]
    total_items = total_events + total_tasks
    
    if len(pages) > 1 and total_items > max_items:  # Only check balance if multiple pages needed
        min_items = min(page_totals)
        max_items_used = max(page_totals)
        
        # Flag severe imbalances (like 8+2 scenarios)
        if max_items_used >= 7 and min_items <= 2:
            logging.warning(f"❌ Distribution validation failed: Severe imbalance - page with {max_items_used} items while another has {min_items}")
            return False
        
        # Check for reasonable distribution: difference should not exceed 3 items
        balance_diff = max_items_used - min_items
        if balance_diff > 3 and total_items > len(pages) * 4:
            logging.warning(f"❌ Distribution validation failed: Poor balance - {balance_diff} item difference between pages")
            return False
    
    # All checks passed
    logging.info(f"✅ Distribution validation passed: {len(pages)} pages with items {page_totals}")
    return True

def distribute_items_across_pages(events: List[Dict[str, Any]], tasks: List[str], max_items: int = 6) -> List[Dict[str, Any]]:
    """
    Intelligently distributes events and tasks across pages with TRUE EVEN DISTRIBUTION.
    Includes built-in validation to ensure balanced output.
    
    Strategy:
    1. Calculate total items and determine optimal distribution UPFRONT
    2. Create target distribution (e.g., 10 items → 5+5, not 8+2)
    3. Distribute items according to targets while prioritizing events first
    4. Validate result before returning to ensure professional balance
    
    Examples:
    - 6 events + 4 tasks = 10 items → 5+5 or 6+4 (balanced)
    - 16 events + 4 tasks = 20 items → 7+7+6 (not 8+8+4)
    - 5 events + 7 tasks = 12 items → 6+6 (not 8+4)
    
    Args:
        events: List of event dictionaries
        tasks: List of task strings
        max_items: Maximum combined items per page (default 8)
    
    Returns:
        List of page data dictionaries with 'events' and 'tasks' keys
    """
    import logging
    
    # Store original counts for validation
    original_events_count = len(events)
    original_tasks_count = len(tasks)
    
    # Safety check to prevent memory issues
    if len(events) + len(tasks) > 1000:
        logging.error("❌ Too many items to distribute! Aborting to prevent memory issues.")
        return [{'events': [], 'tasks': []}]
    
    if not events and not tasks:
        result = [{'events': [], 'tasks': []}]
        validate_distribution_balance(result, original_events_count, original_tasks_count, max_items)
        return result
    
    total_events = len(events)
    total_tasks = len(tasks)
    total_items = total_events + total_tasks
    
    # If everything fits on one page, put it all together
    if total_items <= max_items:
        result = [{
            'events': events,
            'tasks': tasks
        }]
        validate_distribution_balance(result, original_events_count, original_tasks_count, max_items)
        return result
    
    # KEY IMPROVEMENT: Calculate optimal distribution UPFRONT
    min_pages_needed = (total_items + max_items - 1) // max_items  # Ceiling division
    
    # Create target distribution: distribute items as evenly as possible
    # Example: 10 items → [5, 5] not [8, 2]
    # Example: 20 items → [7, 7, 6] not [8, 8, 4]
    target_per_page = total_items // min_pages_needed
    remainder = total_items % min_pages_needed
    
    # Create target list: some pages get +1 item if there's remainder
    page_targets = []
    for i in range(min_pages_needed):
        if i < remainder:
            page_targets.append(target_per_page + 1)
        else:
            page_targets.append(target_per_page)
    
    # Ensure minimum viable pages (at least 4 items per page when splitting)
    min_target = min(4, total_items // min_pages_needed) if min_pages_needed > 1 else 0
    page_targets = [max(target, min_target) for target in page_targets]
    
    logging.info(f"📊 Distributing {total_items} items across {min_pages_needed} pages with targets: {page_targets}")
    
    # Distribute items according to calculated targets
    pages = []
    events_remaining = events.copy()
    tasks_remaining = tasks.copy()
    
    for page_idx, target_items in enumerate(page_targets):
        page_events = []
        page_tasks = []
        items_on_page = 0
        
        # Fill with events first (logical grouping), but respect the target
        while events_remaining and items_on_page < target_items:
            page_events.append(events_remaining.pop(0))
            items_on_page += 1
        
        # Fill remaining space with tasks
        while tasks_remaining and items_on_page < target_items:
            page_tasks.append(tasks_remaining.pop(0))
            items_on_page += 1
        
        # If we're under target and not the last page, try to add one more item
        if (items_on_page < target_items and page_idx < len(page_targets) - 1 and 
            items_on_page < max_items):
            if events_remaining:
                page_events.append(events_remaining.pop(0))
                items_on_page += 1
            elif tasks_remaining:
                page_tasks.append(tasks_remaining.pop(0))
                items_on_page += 1
        
        pages.append({
            'events': page_events,
            'tasks': page_tasks
        })
    
    # Handle any remaining items (shouldn't happen with good calculation)
    if events_remaining or tasks_remaining:
        logging.warning(f"⚠️ Items remaining after distribution: {len(events_remaining)} events, {len(tasks_remaining)} tasks")
        
        # Add to last page if space, otherwise create new page
        if pages and len(pages[-1]['events']) + len(pages[-1]['tasks']) < max_items:
            while events_remaining and len(pages[-1]['events']) + len(pages[-1]['tasks']) < max_items:
                pages[-1]['events'].append(events_remaining.pop(0))
            while tasks_remaining and len(pages[-1]['events']) + len(pages[-1]['tasks']) < max_items:
                pages[-1]['tasks'].append(tasks_remaining.pop(0))
        
        if events_remaining or tasks_remaining:
            pages.append({
                'events': events_remaining,
                'tasks': tasks_remaining
            })
    
    # VALIDATION: Double-check the result before returning
    if validate_distribution_balance(pages, original_events_count, original_tasks_count, max_items):
        page_summary = [len(page['events']) + len(page['tasks']) for page in pages]
        logging.info(f"✅ Distribution completed successfully: {page_summary} items per page")
        return pages
    else:
        logging.error("❌ Distribution failed validation! Returning result anyway as fallback.")
        page_details = []
        for i, page in enumerate(pages):
            events_count = len(page['events'])
            tasks_count = len(page['tasks'])
            page_details.append(f"Page {i+1}: {events_count}e + {tasks_count}t = {events_count + tasks_count}")
        logging.error(f"   Failed distribution: {', '.join(page_details)}")
        return pages

# ==============================================================================
# MAIN ORCHESTRATOR
# ==============================================================================
def main() -> None:
    """Main Orchestrator - Stabilized for Long-term Automation with Critical Fixes."""
    global CHECKLIST_TODAY, CHECKLIST_TOMORROW
    
    # Import sys at function level to ensure it's available in except blocks
    import sys
    
    # Initialize variables that need to be accessible in except blocks
    automation_mode = False
    
    try:
        setup_logging()
        
        # Check for command line arguments
        test_mode = "--test-mode" in sys.argv
        verbose_mode = "--verbose" in sys.argv
        test_connection = "--test-connection" in sys.argv
        diagnose_paths = "--diagnose-paths" in sys.argv
        
        # Adjust logging level if verbose
        if verbose_mode:
            logging.getLogger().setLevel(logging.DEBUG)
            logging.info("Verbose mode enabled")
        
        # Handle path diagnosis mode
        if diagnose_paths:
            try:
                diagnose_output_paths()
                return
            except Exception as e:
                logging.error(f"❌ Path diagnosis failed: {e}")
                sys.exit(1)
        
        # Handle test connection mode
        if test_connection:
            try:
                logging.info("Testing reMarkable connection...")
                working_ip = check_remarkable_availability()
                logging.info(f"✅ reMarkable is reachable at {working_ip}")
                
                logging.info("Testing weather API...")
                weather_data = get_weather_data()
                logging.info(f"✅ Weather data received for {len(weather_data)} locations")
                
                logging.info("All connections working properly")
                return
            except Exception as e:
                logging.error(f"❌ Connection test failed: {e}")
                sys.exit(1)
        
        # Set automation mode detection
        automation_mode = detect_automation_mode()
        
        if test_mode:
            logging.info("🧪 Test mode: Upload to reMarkable will be skipped")
            globals()['UPLOAD_DISABLED'] = True
        
        # Load calendar feeds at runtime with better error handling
        try:
            Config.ICAL_FEEDS = load_calendar_feeds(Config.CALENDAR_FEEDS_FILE)
            logging.info(f"✅ Loaded {len(Config.ICAL_FEEDS)} calendar feeds")
        except FileNotFoundError:
            logging.warning("⚠️  Calendar feeds file not found. Creating example file...")
            Config.CALENDAR_FEEDS_FILE.write_text(
                "# Add your calendar feed URLs here, one per line\n"
                "# Example: https://calendar.google.com/calendar/ical/your-calendar-id/basic.ics\n"
                "# Lines starting with # are comments\n",
                encoding='utf-8'
            )
            Config.ICAL_FEEDS = []
        except Exception as e:
            logging.error(f"❌ Error loading calendar feeds: {e}")
            Config.ICAL_FEEDS = []        # Validate critical configuration
        if not Config.ICAL_FEEDS:
            logging.warning("⚠️  No calendar feeds configured. Dashboard will show no events.")
        
        # Check coordinates are valid (not default 0,0)
        home_coords = Config.LOCATIONS.get("🏠", (0.0, 0.0))
        if home_coords == (0.0, 0.0):
            logging.warning("⚠️  Using default coordinates (0,0). Weather data may be incorrect.")
            logging.warning("⚠️  Set HOME_LAT and HOME_LON in .env file for accurate weather.")
        
        # Check SSH key exists and warn if using default IP
        if not Config.REMARKABLE_SSH_KEY.exists():
            logging.warning(f"⚠️  SSH key not found: {Config.REMARKABLE_SSH_KEY}")
            logging.warning("⚠️  reMarkable upload will be disabled.")
        
        if Config.REMARKABLE_IP == "192.168.1.100":
            logging.info("ℹ️  Using default reMarkable IP (192.168.1.100)")
            logging.info("ℹ️  Update REMARKABLE_IP in .env if your device has a different IP")
        
        # Check template file exists
        template_path = Config.BASE_DIR / Config.TEMPLATE_FILE
        if not template_path.exists():
            logging.error(f"❌ Template file not found: {template_path}")
            raise FileNotFoundError(f"Required template file missing: {template_path}")
        
        # Pre-flight checks with error handling
        try:
            pre_flight_checks()
            logging.info("✅ Step 1/3: Pre-flight checks passed.")
        except Exception as e:
            logging.error(f"❌ Pre-flight checks failed: {e}")
            logging.info("⚠️  Continuing with reduced functionality...")
            globals()['UPLOAD_DISABLED'] = True
        
        # Ensure local output directory exists
        try:
            if Config.LOCAL_OUTPUT_PATH:
                Config.LOCAL_OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
                logging.info(f"✅ Local output directory ready: {Config.LOCAL_OUTPUT_PATH}")
        except Exception as e:
            logging.warning(f"⚠️  Could not create local output directory: {e}")
            logging.warning("⚠️  Local PDF backup may not work correctly")
        
        # Fetch all data with comprehensive error handling
        ics_data = ""
        weather = {}
        
        try:
            all_data = fetch_all_data()
            ics_data = all_data.get("ics_data", "")
            weather = all_data.get("weather", {})
            logging.info(f"External data fetch completed - ICS: {len(ics_data)} chars, Weather: {len(weather)} locations")
        except Exception as e:
            logging.error(f"Failed to fetch external data: {e}")
            if automation_mode:
                logging.info("Automation mode: Using empty fallback data and continuing...")
            else:
                logging.info("Using empty fallback data...")
        
        logging.info("⚙️ Step 3/3: Generating dashboard...")
        now = arrow.now(Config.TIMEZONE_LOCAL_STR)
        
        # Parse events with comprehensive error handling
        all_events = []
        try:
            if ics_data:
                parsed_events = parse_events(ics_data, Config.TIMEZONE_LOCAL_STR)
                all_events = validate_events(parsed_events) if parsed_events else []
                logging.info(f"Successfully parsed {len(all_events)} events")
            else:
                logging.warning("No calendar data available, proceeding with empty events")
        except Exception as e:
            logging.error(f"Failed to parse events: {e}")
            if automation_mode:
                logging.info("Automation mode: Proceeding with empty events list...")
            all_events = []
        today_start = now.floor('day')
        today_end = today_start.shift(days=1)
        tomorrow_start = today_end
        tomorrow_end = tomorrow_start.shift(days=1)

        def is_event_for_day(event, day_start, day_end):
            """Check if an event falls within a specific day, with defensive handling."""
            try:
                # Defensive: ensure begin_local and end_local are not None
                begin_local = event.get('begin_local')
                end_local = event.get('end_local')
                if begin_local is None or end_local is None:
                    return False
                if event.get('all_day'):
                    # Defensive: ensure begin_local supports floor()
                    try:
                        return begin_local.floor('day') == day_start
                    except Exception:
                        return False
                else:
                    return begin_local < day_end and end_local > day_start
            except Exception as e:
                logging.warning(f"Error checking event for day: {e}")
                return False

        # Filter events by day with error handling
        try:
            today_events = [event for event in all_events if is_event_for_day(event, today_start, today_end)]
            tomorrow_events = [event for event in all_events if is_event_for_day(event, tomorrow_start, tomorrow_end)]
        except Exception as e:
            logging.error(f"Error filtering events: {e}")
            today_events = []
            tomorrow_events = []

        # Process events for template (add icons and display times)
        try:
            today_events = process_events_for_template(today_events) if today_events else []
            tomorrow_events = process_events_for_template(tomorrow_events) if tomorrow_events else []
            
            # Add strategic writing spaces after every 3 events for note-taking
            today_events = add_strategic_writing_spaces(today_events) if today_events else []
            tomorrow_events = add_strategic_writing_spaces(tomorrow_events) if tomorrow_events else []
        except Exception as e:
            logging.error(f"Error processing events for template: {e}")
            today_events = []
            tomorrow_events = []

        # Process weather data with error handling
        try:
            # Only use the emoji (first character) as location label for weather
            weather_data_for_template = []
            for loc, forecast_data in (weather.items() if weather else []):
                try:
                    location_label = loc.split()[0] if loc else ''
                    narrative = generate_weather_narrative(forecast_data) if forecast_data else "Weather data unavailable."
                    weather_data_for_template.append({
                        "location": location_label,
                        "narrative": narrative
                    })
                except Exception as e:
                    logging.warning(f"Error processing weather for location {loc}: {e}")
                    weather_data_for_template.append({
                        "location": loc.split()[0] if loc else '🌦️',
                        "narrative": "Weather data unavailable."
                    })
        except Exception as e:
            logging.error(f"Error processing weather data: {e}")
            weather_data_for_template = []
        
        # Generate tomorrow weather data with error handling
        try:
            tomorrow_weather_data_for_template = []
            for loc, forecast_data in (weather.items() if weather else []):
                try:
                    if forecast_data:
                        location_label = loc.split()[0] if loc else ''
                        narrative = generate_weather_narrative(forecast_data, for_tomorrow=True) if forecast_data else "Weather data unavailable."
                        tomorrow_weather_data_for_template.append({
                            "location": location_label,
                            "narrative": narrative
                        })
                except Exception as e:
                    logging.warning(f"Error processing tomorrow weather for location {loc}: {e}")
                    tomorrow_weather_data_for_template.append({
                        "location": loc.split()[0] if loc else '🌦️',
                        "narrative": "Weather data unavailable."
                    })
        except Exception as e:
            logging.error(f"Error processing tomorrow weather data: {e}")
            tomorrow_weather_data_for_template = []
        
        logging.info(f"Weather data prepared for template: {weather_data_for_template}")
        logging.info(f"Tomorrow weather data prepared for template: {tomorrow_weather_data_for_template}")
        logging.info(f"Today events: {today_events}")
        logging.info(f"Tomorrow events: {tomorrow_events}")
        logging.info(f"Tomorrow weather data for template: {tomorrow_weather_data_for_template}")

        # --- Build pages: distribute events and tasks across pages with error handling ---
        try:
            page_contexts = []
            global_page_number = 0  # Global page counter
            
            # Distribute today's events and tasks across pages
            try:
                today_pages = distribute_items_across_pages(today_events, CHECKLIST_TODAY, Config.MAX_ITEMS_PER_PAGE)
            except Exception as e:
                logging.error(f"Error distributing today's items: {e}")
                today_pages = []
            
            # Add today pages
            for page_idx, page_data in enumerate(today_pages):
                try:
                    is_first_today_page = (page_idx == 0)
                    
                    page_contexts.append(build_page_context(
                        global_page_number,
                        {
                            'today_events': page_data.get('events', []), 
                            'tomorrow_events': [],
                            'today_tasks': page_data.get('tasks', []),
                            'tomorrow_tasks': []
                        },
                        now,
                        1,  # Will be updated later
                        bool(today_events),  # has_today_events
                        bool(tomorrow_events),  # has_tomorrow_events
                        bool(CHECKLIST_TODAY),  # has_today_tasks
                        bool(CHECKLIST_TOMORROW),  # has_tomorrow_tasks
                        weather_data_for_template if is_first_today_page else [],
                        None,  # first_tomorrow_page_idx
                        today_events,  # all_today_events
                        tomorrow_events,  # all_tomorrow_events
                        CHECKLIST_TODAY,  # all_today_tasks
                        CHECKLIST_TOMORROW  # all_tomorrow_tasks
                    ))
                    global_page_number += 1
                except Exception as e:
                    logging.error(f"Error building today page context {page_idx}: {e}")
                    # Skip this page and continue
            
            # If no today events/tasks, add an empty today page with weather
            if not today_pages:
                try:
                    page_contexts.append(build_page_context(
                        global_page_number,
                        {'today_events': [], 'tomorrow_events': [], 'today_tasks': [], 'tomorrow_tasks': []},
                        now,
                        1,  # Will be updated later
                        False,
                        bool(tomorrow_events),
                        False,  # has_today_tasks (no tasks on empty page)
                        bool(CHECKLIST_TOMORROW),  # has_tomorrow_tasks
                        weather_data_for_template,
                        None,  # first_tomorrow_page_idx
                        today_events,  # all_today_events
                        tomorrow_events,  # all_tomorrow_events
                        CHECKLIST_TODAY,  # all_today_tasks
                        CHECKLIST_TOMORROW  # all_tomorrow_tasks
                    ))
                    global_page_number += 1
                except Exception as e:
                    logging.error(f"Error building empty today page: {e}")
            
            # Add today notes page at the end of today's section
            try:
                page_contexts.append(create_notes_page_context('today', now, global_page_number + 1, 1))  # Will be updated later
                global_page_number += 1
            except Exception as e:
                logging.error(f"Error creating today notes page: {e}")

            # Distribute tomorrow's events and tasks across pages
            try:
                tomorrow_pages = distribute_items_across_pages(tomorrow_events, CHECKLIST_TOMORROW, Config.MAX_ITEMS_PER_PAGE)
            except Exception as e:
                logging.error(f"Error distributing tomorrow's items: {e}")
                tomorrow_pages = []
            
            first_tomorrow_page_idx = global_page_number  # Track where tomorrow section starts
            
            # Add tomorrow pages
            for page_idx, page_data in enumerate(tomorrow_pages):
                try:
                    is_first_tomorrow_page = (page_idx == 0)
                    
                    page_contexts.append(build_page_context(
                        global_page_number,
                        {
                            'today_events': [], 
                            'tomorrow_events': page_data.get('events', []),
                            'today_tasks': [],
                            'tomorrow_tasks': page_data.get('tasks', [])
                        },
                        now,
                        1,  # Will be updated later
                        bool(today_events),  # has_today_events
                        bool(tomorrow_events),  # has_tomorrow_events
                        bool(CHECKLIST_TODAY),  # has_today_tasks
                        bool(CHECKLIST_TOMORROW),  # has_tomorrow_tasks
                        tomorrow_weather_data_for_template if is_first_tomorrow_page else [],
                        first_tomorrow_page_idx,  # Always pass this for overflow detection
                        today_events,  # all_today_events
                        tomorrow_events,  # all_tomorrow_events
                        CHECKLIST_TODAY,  # all_today_tasks
                        CHECKLIST_TOMORROW  # all_tomorrow_tasks
                    ))
                    global_page_number += 1
                except Exception as e:
                    logging.error(f"Error building tomorrow page context {page_idx}: {e}")
                    # Skip this page and continue
            
            # If no tomorrow events/tasks, add an empty tomorrow page with weather
            if not tomorrow_pages:
                try:
                    page_contexts.append(build_page_context(
                        global_page_number,
                        {'today_events': [], 'tomorrow_events': [], 'today_tasks': [], 'tomorrow_tasks': []},
                        now,
                        1,  # Will be updated later
                        bool(today_events),
                        False,
                        bool(CHECKLIST_TODAY),  # has_today_tasks
                        False,  # has_tomorrow_tasks (no tasks on empty page)
                        tomorrow_weather_data_for_template,
                        first_tomorrow_page_idx,
                        today_events,  # all_today_events
                        tomorrow_events,  # all_tomorrow_events
                        CHECKLIST_TODAY,  # all_today_tasks
                        CHECKLIST_TOMORROW  # all_tomorrow_tasks
                    ))
                    global_page_number += 1
                except Exception as e:
                    logging.error(f"Error building empty tomorrow page: {e}")
            
            # Add tomorrow notes page at the end of tomorrow's section
            try:
                page_contexts.append(create_notes_page_context('tomorrow', now, global_page_number + 1, 1))  # Will be updated later
                global_page_number += 1
            except Exception as e:
                logging.error(f"Error creating tomorrow notes page: {e}")

            # Ensure we have at least one page
            if not page_contexts:
                logging.warning("No pages created, adding fallback page")
                try:
                    page_contexts.append(build_page_context(
                        0,
                        {'today_events': [], 'tomorrow_events': [], 'today_tasks': [], 'tomorrow_tasks': []},
                        now,
                        1,
                        False,
                        False,
                        False,  # has_today_tasks
                        False,  # has_tomorrow_tasks
                        weather_data_for_template,
                        None,  # first_tomorrow_page_idx
                        [],  # all_today_events
                        [],  # all_tomorrow_events
                        [],  # all_today_tasks
                        []  # all_tomorrow_tasks
                    ))
                except Exception as e:
                    logging.error(f"Error creating fallback page: {e}")
                    # Create minimal fallback context
                    page_contexts.append({
                        'events': [],
                        'tasks': [],
                        'page_number': 1,
                        'total_pages': 1,
                        'last_updated_str': now.format('HH:mm ZZZ, dddd, MMMM D'),
                        'day': 'today',
                        'epigraph': None,
                        'weather_data': weather_data_for_template,
                        'is_overflow_events_page': False,
                        'is_overflow_tasks_page': False,
                        'show_events_header': False,
                        'show_tasks_header': False,
                        'events_continuation_text': "",
                        'tasks_continuation_text': "",
                    })

            logging.info(f"   -> Prepared {len(page_contexts)} page(s) for rendering.")
            
            # Debug: log each page context
            for i, ctx in enumerate(page_contexts):
                logging.info(f"Page {i+1}: day={ctx.get('day')}, events={len(ctx.get('events', []))}, tasks={len(ctx.get('tasks', []))}, epigraph={ctx.get('epigraph') is not None}, weather={ctx.get('weather_data') is not None}")
        except Exception as e:
            logging.error(f"Fatal error during page context building: {e}")
            # Create minimal fallback
            page_contexts = [{
                'events': [],
                'tasks': [],
                'page_number': 1,
                'total_pages': 1,
                'last_updated_str': now.format('HH:mm ZZZ, dddd, MMMM D'),
                'day': 'today',
                'epigraph': None,
                'weather_data': weather_data_for_template
            }]
        total_pages = len(page_contexts)
        
        # Update all page contexts with correct total pages
        for ctx in page_contexts:
            ctx['total_pages'] = total_pages

        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                day_initials = ['M', 'T', 'W', 'R', 'F', 'Sa', 'Su']
                weekday_idx = now.weekday()
                day_initial = day_initials[weekday_idx]
                base_name = f"NMS_{now.format('YYYY_MM_DD')}_{day_initial}"
                output_dir = Config.LOCAL_OUTPUT_PATH if Config.LOCAL_OUTPUT_PATH else Path('.')
                output_dir.mkdir(parents=True, exist_ok=True)
                
                # Generate PDF with error handling
                try:
                    pdf_file_path = generate_multipage_pdf(page_contexts, Path(temp_dir))
                    consistent_pdf_path = Path(temp_dir) / f"{base_name}.pdf"
                    shutil.copy(pdf_file_path, consistent_pdf_path)
                    logging.info(f"Successfully generated PDF: {consistent_pdf_path}")
                except Exception as e:
                    logging.error(f"Failed to generate PDF: {e}")
                    raise
                
                # Save local copy with error handling and fallbacks
                if Config.LOCAL_OUTPUT_PATH:
                    try:
                        # First, try the configured path
                        dest_path = output_dir / f"{base_name}.pdf"
                        
                        # Ensure directory exists and is writable
                        try:
                            output_dir.mkdir(parents=True, exist_ok=True)
                            # Test write access with a small test file
                            test_file = output_dir / "write_test.tmp"
                            test_file.write_text("test")
                            test_file.unlink()  # Remove test file
                        except Exception as dir_e:
                            logging.warning(f"Primary output directory not accessible: {dir_e}")
                            raise
                        
                        shutil.copy(consistent_pdf_path, dest_path)
                        logging.info(f"✅ Saved local copy to: {dest_path}")
                        
                    except Exception as e:
                        logging.error(f"Failed to save to primary location: {e}")
                        
                        # Fallback 1: Try current script directory
                        try:
                            fallback_path = Config.BASE_DIR / f"{base_name}.pdf"
                            shutil.copy(consistent_pdf_path, fallback_path)
                            logging.info(f"✅ Saved fallback copy to script directory: {fallback_path}")
                        except Exception as fallback_e:
                            logging.error(f"Fallback to script directory failed: {fallback_e}")
                            
                            # Fallback 2: Try user's Documents folder
                            try:
                                import os
                                docs_path = Path.home() / "Documents" / "Huang_Di_Dashboard"
                                docs_path.mkdir(parents=True, exist_ok=True)
                                final_fallback = docs_path / f"{base_name}.pdf"
                                shutil.copy(consistent_pdf_path, final_fallback)
                                logging.info(f"✅ Saved final fallback copy to Documents: {final_fallback}")
                            except Exception as docs_e:
                                logging.error(f"All local save attempts failed: {docs_e}")
                                logging.warning("⚠️ PDF was generated but could not be saved locally. Check permissions on output directories.")
                else:
                    logging.info("No local output path configured, skipping local save")
                
                # Upload to reMarkable with error handling
                upload_disabled = globals().get('UPLOAD_DISABLED', False)
                if Config.REMARKABLE_IP and not upload_disabled:
                    try:
                        check_remarkable_availability()
                        visible_name = page_contexts[0].get('visible_name_str', base_name) if page_contexts else base_name
                        upload_to_remarkable(consistent_pdf_path, Path(temp_dir), total_pages, base_name, visible_name)
                        logging.info("Successfully uploaded to reMarkable")
                    except Exception as e:
                        logging.error(f"Failed to upload to reMarkable: {e}")
                        # Continue execution even if upload fails
                elif upload_disabled:
                    logging.info("Upload to reMarkable skipped - SSH tools or keys not available")
                else:
                    logging.info("reMarkable IP not configured, skipping upload")
                    
            except Exception as e:
                logging.error(f"Error during PDF generation and upload process: {e}")
                raise
        
        logging.info("✅ Mission accomplished. The Imperial Dashboard is updated.")
    except Exception as e:
        logging.critical(f"A system-wide failure has occurred: {e}", exc_info=True)
        
        # If in automation mode, try to create an emergency dashboard
        if automation_mode:
            try:
                logging.info("Automation mode: Attempting to create emergency dashboard...")
                now = arrow.now(Config.TIMEZONE_LOCAL_STR)
                create_emergency_dashboard(now)
                logging.info("Emergency dashboard created successfully")
            except Exception as emergency_e:
                logging.critical(f"Failed to create emergency dashboard: {emergency_e}")
        
        sys.exit(1)

# REMOVED: auto_correct_rrule_until - duplicate of convert_rrule_until_to_naive

def convert_rrule_until_to_naive(rrule_str: str, timezone_str: str) -> str:
    """
    Convert RRULE UNTIL values from UTC format (with Z suffix) to naive format in local timezone.
    This ensures consistency when using naive dtstart with rrulestr().
    
    Args:
        rrule_str: Raw RRULE string from calendar
        timezone_str: Target timezone string
    
    Returns:
        RRULE string with UNTIL in naive local time format
    """
    import re
    
    # Look for UNTIL=<datetime>Z pattern (UTC format)
    until_pattern = r'UNTIL=(\d{8}T\d{6})Z'
    match = re.search(until_pattern, rrule_str)
    
    if not match:
        return rrule_str
    
    until_value = match.group(1)
    
    try:
        # Parse the UNTIL value as UTC time
        until_utc = datetime.strptime(until_value, '%Y%m%dT%H%M%S')
        until_utc = until_utc.replace(tzinfo=timezone.utc)
        
        # Convert to local timezone
        local_tz = pytz.timezone(timezone_str)
        until_local = until_utc.astimezone(local_tz)
        
        # Format as naive local time (no Z suffix)
        until_naive_str = until_local.strftime('%Y%m%dT%H%M%S')
        
        # Replace in the RRULE string
        corrected_rrule = rrule_str.replace(f'UNTIL={until_value}Z', f'UNTIL={until_naive_str}')
        
        logging.info(f"Converted RRULE UNTIL from UTC to naive local: {until_value}Z -> {until_naive_str}")
        return corrected_rrule
    
    except (ValueError, AttributeError) as e:
        logging.warning(f"Could not convert RRULE UNTIL value {until_value}Z: {e}")
        return rrule_str

def _validate_and_sanitize_contexts(contexts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Validates and sanitizes page contexts to ensure template safety."""
    if not contexts:
        return [_create_safe_default_context()]
    
    sanitized = []
    for ctx in contexts:
        # Ensure all required fields exist with safe defaults
        safe_ctx = {
            'events': ctx.get('events', []),
            'tasks': ctx.get('tasks', []),
            'blank_entries': ctx.get('blank_entries', []),
            'page_number': ctx.get('page_number', 1),
            'total_pages': ctx.get('total_pages', 1),
            'last_updated_str': ctx.get('last_updated_str', 'Unknown'),
            'day': ctx.get('day', 'today'),
            'epigraph': ctx.get('epigraph'),
            'weather_data': ctx.get('weather_data'),
            'today_header_str': ctx.get('today_header_str', 'Dashboard'),
            'tomorrow_header_str': ctx.get('tomorrow_header_str', 'Tomorrow'),
            'visible_name_str': ctx.get('visible_name_str', 'Dashboard'),
            'pdf_filename_str': ctx.get('pdf_filename_str', 'dashboard'),
            'has_today_events': ctx.get('has_today_events', False),
            'has_tomorrow_events': ctx.get('has_tomorrow_events', False),
            'has_today_tasks': ctx.get('has_today_tasks', False),
            'has_tomorrow_tasks': ctx.get('has_tomorrow_tasks', False),
            'today_date_str': ctx.get('today_date_str', 'Today'),
            'is_overflow_events_page': ctx.get('is_overflow_events_page', False),
            'is_overflow_tasks_page': ctx.get('is_overflow_tasks_page', False),
            'show_events_header': ctx.get('show_events_header', False),
            'show_tasks_header': ctx.get('show_tasks_header', False),
            'events_continuation_text': ctx.get('events_continuation_text', ''),
            'tasks_continuation_text': ctx.get('tasks_continuation_text', ''),
        }
        
        # Ensure nested structures are safe
        if not isinstance(safe_ctx['events'], list):
            safe_ctx['events'] = []
        if not isinstance(safe_ctx['tasks'], list):
            safe_ctx['tasks'] = []
        if not isinstance(safe_ctx['blank_entries'], list):
            safe_ctx['blank_entries'] = []
            
        sanitized.append(safe_ctx)
    
    return sanitized

def _create_safe_default_context() -> Dict[str, Any]:
    """Creates a minimal safe context for emergency use."""
    return {
        'events': [],
        'tasks': ['Dashboard generation in progress...'],
        'blank_entries': [],
        'page_number': 1,
        'total_pages': 1,
        'last_updated_str': 'Emergency Mode',
        'day': 'today',
        'epigraph': None,
        'weather_data': None,
        'today_header_str': 'Emergency Dashboard',
        'tomorrow_header_str': 'Tomorrow',
        'visible_name_str': 'Emergency',
        'pdf_filename_str': 'emergency',
        'has_today_events': False,
        'has_tomorrow_events': False,
        'has_today_tasks': True,
        'has_tomorrow_tasks': False,
        'today_date_str': 'Emergency',
        'is_overflow_events_page': False,
        'is_overflow_tasks_page': False,
        'show_events_header': False,
        'show_tasks_header': True,
        'events_continuation_text': '',
        'tasks_continuation_text': '',
    }

def _render_template_with_fallback(contexts: List[Dict[str, Any]], temp_path: Path) -> str:
    """Renders template with comprehensive fallback system."""
    try:
        # Primary: Try normal Jinja2 template rendering
        env = Environment(loader=FileSystemLoader(Config.BASE_DIR))
        template = env.get_template(Config.TEMPLATE_FILE)
        
        rendered_html = template.render(
            page_contexts=contexts,
            epigraph=Config.EPIGRAPH if Config.EPIGRAPH else {'quote': '', 'author': ''},
            weather_data=[c.get('weather_data', []) for c in contexts][0] if contexts else []
        )
        
        logging.info("✅ Template rendered successfully")
        return rendered_html
        
    except Exception as template_error:
        logging.warning(f"⚠️ Template rendering failed: {template_error}")
        logging.info("📄 Falling back to emergency HTML generation...")
        
        try:
            # Secondary: Generate emergency HTML without Jinja2
            emergency_html = _generate_emergency_html(contexts)
            logging.info("✅ Emergency HTML generated successfully")
            return emergency_html
            
        except Exception as emergency_error:
            logging.error(f"❌ Emergency HTML generation failed: {emergency_error}")
            logging.info("📄 Falling back to minimal HTML...")
            
            try:
                # Tertiary: Generate minimal HTML that should always work
                minimal_html = _generate_minimal_html()
                logging.info("✅ Minimal HTML generated as final fallback")
                return minimal_html
                
            except Exception as minimal_error:
                logging.critical(f"❌ Even minimal HTML generation failed: {minimal_error}")
                # Last resort: return basic HTML string
                return "<html><body><h1>Dashboard Generation Failed</h1><p>All template fallbacks failed.</p></body></html>"

def _generate_emergency_html(contexts: List[Dict[str, Any]]) -> str:
    """Generates emergency HTML without template engine dependencies."""
    html_parts = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        "<title>Emergency Dashboard</title>",
        "<style>",
        "body { font-family: Arial, sans-serif; margin: 20px; }",
        ".page { page-break-after: always; margin-bottom: 40px; }",
        ".header { font-size: 18px; font-weight: bold; margin-bottom: 20px; }",
        ".events, .tasks { margin-bottom: 20px; }",
        ".item { margin-bottom: 10px; padding: 5px; border-left: 3px solid #ccc; }",
        "</style>",
        "</head>",
        "<body>"
    ]
    
    for i, ctx in enumerate(contexts):
        html_parts.append(f'<div class="page">')
        
        # Header
        today_header = ctx.get('today_header_str', 'Dashboard')
        html_parts.append(f'<div class="header">{today_header}</div>')
        
        # Page info
        page_num = ctx.get('page_number', i + 1)
        total_pages = ctx.get('total_pages', len(contexts))
        html_parts.append(f'<p>Page {page_num} of {total_pages}</p>')
        
        # Events
        events = ctx.get('events', [])
        if events:
            html_parts.append('<div class="events"><h3>Events</h3>')
            for event in events:
                if isinstance(event, dict):
                    summary = event.get('summary', 'Event')
                    time = event.get('display_time', '')
                    html_parts.append(f'<div class="item">{time} {summary}</div>')
                else:
                    html_parts.append(f'<div class="item">{str(event)}</div>')
            html_parts.append('</div>')
        
        # Tasks
        tasks = ctx.get('tasks', [])
        if tasks:
            html_parts.append('<div class="tasks"><h3>Tasks</h3>')
            for task in tasks:
                html_parts.append(f'<div class="item">{str(task)}</div>')
            html_parts.append('</div>')
        
        html_parts.append('</div>')
    
    html_parts.extend(["</body>", "</html>"])
    
    return '\n'.join(html_parts)

def _generate_minimal_html() -> str:
    """Generates absolute minimal HTML as final fallback."""
    return """<!DOCTYPE html>
<html>
<head>
    <title>Minimal Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        @page { size: 5.3in 7.0in; margin: 0.5in; }
    </style>
</head>
<body>
    <h1>Emergency Dashboard</h1>
    <p>Dashboard generated in emergency mode due to template errors.</p>
    <p>Last updated: Emergency Mode</p>
    <div style="margin-top: 50px;">
        <h2>Status</h2>
        <p>✅ System is operational</p>
        <p>⚠️ Template rendering failed - using fallback</p>
        <p>📋 Check logs for details</p>
    </div>
</body>
</html>"""

if __name__ == "__main__":
    try:
        main()
        logging.info("✅ Dashboard generation completed successfully!")
    except KeyboardInterrupt:
        logging.info("🛑 Script interrupted by user.")
        sys.exit(1)
    except Exception as e:
        logging.error(f"❌ Critical error in main(): {e}")
        logging.error("📋 Full traceback:")
        import traceback
        logging.error(traceback.format_exc())
        
        # Create emergency dashboard for automation reliability
        try:
            logging.info("🚨 Creating emergency dashboard...")
            emergency_html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Emergency Dashboard</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .error {{ color: red; font-weight: bold; }}
        .timestamp {{ color: gray; font-size: 0.9em; }}
    </style>
</head>
<body>
    <h1>🚨 Emergency Dashboard</h1>
    <p class="error">Main dashboard generation failed.</p>
    <p class="timestamp">Generated: {arrow.now().format('YYYY-MM-DD HH:mm:ss')}</p>
    <h2>Error Details:</h2>
    <p><code>{str(e)}</code></p>
    <h2>Troubleshooting:</h2>
    <ul>
        <li>Check {Config.LOG_FILE} for detailed error information</li>
        <li>Verify internet connectivity</li>
        <li>Ensure .env file is properly configured</li>
        <li>Check calendar_feeds.txt exists and has valid URLs</li>
    </ul>
</body>
</html>"""
            
            # Save emergency dashboard
            emergency_path = Config.BASE_DIR / "emergency_dashboard.html"
            emergency_path.write_text(emergency_html, encoding='utf-8')
            logging.info(f"✅ Emergency dashboard saved to: {emergency_path}")
            
            # For automation: exit with success to avoid breaking scheduled runs
            logging.info("🔄 Exiting with success for automation reliability...")
            sys.exit(0)
            
        except Exception as emergency_error:
            logging.error(f"❌ Emergency dashboard creation failed: {emergency_error}")
            sys.exit(1)