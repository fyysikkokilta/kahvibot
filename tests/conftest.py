import sys
import tempfile
import types
from pathlib import Path


def _make_test_config():
    tmp_dir = Path(tempfile.mkdtemp(prefix="omatsufe_test_"))
    data_dir = tmp_dir / "data"
    data_dir.mkdir()

    cfg = types.ModuleType("config")
    cfg.BASE_DIR = tmp_dir
    cfg.DATA_DIR = data_dir
    cfg.TELEGRAM_TOKEN = "TEST_TOKEN"
    cfg.MQTT_BROKER = "localhost"
    cfg.MQTT_PORT = 1883
    cfg.MQTT_USER = "test"
    cfg.MQTT_PASS = "test"
    cfg.DEVICES = ["vasen", "oikea"]
    cfg.MQTT_BASE_TOPIC = "zigbee2mqtt"
    cfg.DEFAULT_DEVICE = "oikea"
    cfg.BREW_THRESHOLD = 300.0
    cfg.HEAT = 100.0
    cfg.PLOT_HOURS = 24.0
    cfg.CUP_CALIBRATION = []
    cfg.ADMIN_CHAT_ID = None
    cfg.RATE_LIMIT_SECONDS = 0.0
    return cfg


# Installed before any test module imports plot/bot/mqtt_logger, since none of
# those repos ship a real config.py (it's gitignored, user-provided secrets).
sys.modules.setdefault("config", _make_test_config())
