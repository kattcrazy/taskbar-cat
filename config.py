import logging
import os
import sys

import yaml

logger = logging.getLogger("taskbar_cat")

DEFAULT_SETTINGS = {
    "size": 150,
    "y_offset": 15,
    "x_offset": -10,
    "monitor_mode": "primary",
}


def get_config_dir():
    """%APPDATA%\\TaskbarCat (Roaming)."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        appdata = os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    return os.path.join(appdata, "TaskbarCat")


def ensure_config_dir():
    d = get_config_dir()
    os.makedirs(d, exist_ok=True)
    return d


def get_config_yaml_path():
    return os.path.join(get_config_dir(), "config.yaml")


def get_log_path():
    return os.path.join(get_config_dir(), "taskbar_cat.log")


def _merge_validated_settings(raw):
    """Merge dict into validated defaults."""
    if not isinstance(raw, dict):
        return DEFAULT_SETTINGS.copy()
    result = DEFAULT_SETTINGS.copy()
    try:
        if "size" in raw and 50 <= int(raw["size"]) <= 500:
            result["size"] = int(raw["size"])
        if "y_offset" in raw and -200 <= int(raw["y_offset"]) <= 200:
            result["y_offset"] = int(raw["y_offset"])
        if "x_offset" in raw and -500 <= int(raw["x_offset"]) <= 500:
            result["x_offset"] = int(raw["x_offset"])
        if raw.get("monitor_mode") in ("primary", "all"):
            result["monitor_mode"] = raw["monitor_mode"]
    except (TypeError, ValueError):
        pass
    return result


def load_settings():
    """Load settings from %APPDATA%\\TaskbarCat\\config.yaml."""
    yaml_path = get_config_yaml_path()
    if not os.path.exists(yaml_path):
        return DEFAULT_SETTINGS.copy()
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return _merge_validated_settings(data if data is not None else {})
    except Exception as e:
        logger.exception("Error loading YAML settings: %s", e)
        return DEFAULT_SETTINGS.copy()


def save_settings(size, y_offset, x_offset, monitor_mode):
    """Save settings to AppData YAML (skips if -testing flag is set)."""
    if "-testing" in sys.argv or "--testing" in sys.argv:
        return

    ensure_config_dir()
    settings = {
        "size": int(size),
        "y_offset": int(y_offset),
        "x_offset": int(x_offset),
        "monitor_mode": monitor_mode,
    }

    try:
        with open(get_config_yaml_path(), "w", encoding="utf-8") as f:
            yaml.safe_dump(
                settings,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )
    except Exception as e:
        logger.exception("Error saving settings: %s", e)


def configure_logging():
    """Configure logging to a local file and console fallback."""
    if logger.handlers:
        return

    logger.setLevel(logging.INFO)
    ensure_config_dir()
    log_path = get_log_path()
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    try:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        pass

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
