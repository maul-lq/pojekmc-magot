from __future__ import annotations

import json
import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

import altair as alt
import numpy as np
import pandas as pd
import paho.mqtt.client as mqtt
import streamlit as st
import streamlit.components.v1 as components
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score



def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


DATA_FILE = Path(os.getenv("IOT_DATA_FILE", "data.csv"))
MQTT_HOST = os.getenv("MQTT_HOST", "192.168.18.43")
MQTT_PORT = _env_int("MQTT_PORT", 1883)
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "esp32/sensor_data")
MAX_HISTORY = _env_int("MAX_HISTORY", 2000)
MIN_TRAINING_SAMPLES = _env_int("MIN_TRAINING_SAMPLES", 24)
LAG_WINDOW = _env_int("LAG_WINDOW", 6)
DISPLAY_TIMEZONE = os.getenv("DISPLAY_TIMEZONE", "Asia/Jakarta")
OUTLIER_Z_THRESHOLD = _env_float("OUTLIER_Z_THRESHOLD", 4.5)
MIN_OUTLIER_SAMPLES = _env_int("MIN_OUTLIER_SAMPLES", 12)
TEMP_OUTLIER_MIN_DELTA = _env_float("TEMP_OUTLIER_MIN_DELTA", 0.8)
HUM_OUTLIER_MIN_DELTA = _env_float("HUM_OUTLIER_MIN_DELTA", 3.0)


st.set_page_config(
    page_title="IoT ESP32 Dashboard",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown(
    """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap');
        :root {
            --ink: #f3f2f8;
            --ink-muted: #c8c5d6;
            --accent: #348ba8;
            --accent-2: #bce784;
            --card: rgba(80, 58, 85, 0.86);
            --card-border: rgba(83, 82, 117, 0.45);
            --glow: rgba(52, 139, 168, 0.35);
        }
        .stApp {
            background: radial-gradient(circle at top left, rgba(83, 82, 117, 0.9), rgba(80, 58, 85, 0.98) 58%);
            color: var(--ink);
            font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
        }
        .stApp::before {
            content: "";
            position: fixed;
            inset: -10% -20% auto -20%;
            height: 55vh;
            background: radial-gradient(circle at 18% 18%, rgba(52, 139, 168, 0.28), transparent 60%),
                        radial-gradient(circle at 85% 15%, rgba(188, 231, 132, 0.22), transparent 55%);
            filter: blur(0px);
            z-index: 0;
            pointer-events: none;
        }
        header[data-testid="stHeader"],
        div[data-testid="stToolbar"],
        div[data-testid="stDecoration"] {
            visibility: hidden;
            height: 0;
        }
        div[data-baseweb="tab-list"] {
            gap: 0.4rem;
            background: rgba(80, 58, 85, 0.55);
            border: 1px solid rgba(83, 82, 117, 0.5);
            border-radius: 999px;
            padding: 0.35rem 0.45rem;
        }
        button[data-baseweb="tab"] {
            color: var(--ink-muted);
            background: transparent;
            border-radius: 999px;
            padding: 0.25rem 0.9rem;
            font-weight: 600;
            letter-spacing: 0.02em;
        }
        button[data-baseweb="tab"][aria-selected="true"] {
            color: #503a55;
            background: linear-gradient(135deg, rgba(52, 139, 168, 0.95), rgba(188, 231, 132, 0.9));
            box-shadow: 0 6px 18px rgba(80, 58, 85, 0.35);
        }
        section[data-testid="stSidebar"] {
            border-right: 1px solid rgba(83, 82, 117, 0.45);
        }
        .block-container {
            padding-top: 1.2rem;
            padding-bottom: 2rem;
            position: relative;
            z-index: 1;
        }
        h1, h2, h3, h4 {
            font-family: "Space Grotesk", "Segoe UI", sans-serif;
        }
        .hero-card, .metric-card {
            background: var(--card);
            border: 1px solid var(--card-border);
            border-radius: 18px;
            padding: 1rem 1.1rem;
            box-shadow: 0 18px 50px rgba(0, 0, 0, 0.2);
            animation: fadeUp 0.8s ease both;
        }
        .hero-title {
            font-size: 2.2rem;
            font-weight: 800;
            line-height: 1.05;
            margin: 0;
            color: #f4f7fb;
        }
        .hero-subtitle {
            margin-top: 0.35rem;
            color: #b8c7df;
        }
        .pill {
            display: inline-block;
            padding: 0.26rem 0.7rem;
            border-radius: 999px;
            background: rgba(52, 139, 168, 0.2);
            color: #d8f1f7;
            border: 1px solid rgba(52, 139, 168, 0.45);
            font-size: 0.84rem;
            margin-right: 0.45rem;
            margin-top: 0.25rem;
        }
        .pill.gold {
            background: rgba(188, 231, 132, 0.22);
            border-color: rgba(188, 231, 132, 0.55);
            color: #f2f8e7;
        }
        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(6, minmax(0, 1fr));
            gap: 0.9rem;
            margin: 1rem 0 0.4rem 0;
        }
        .kpi-card {
            position: relative;
            padding: 1rem 1.1rem;
            border-radius: 18px;
            background: rgba(83, 82, 117, 0.55);
            border: 1px solid rgba(52, 139, 168, 0.3);
            box-shadow: 0 12px 35px rgba(0, 0, 0, 0.25);
            overflow: hidden;
        }
        .kpi-card::after {
            content: "";
            position: absolute;
            inset: auto -30% -40% -30%;
            height: 65%;
            background: radial-gradient(circle, rgba(52, 139, 168, 0.28), transparent 60%);
            opacity: 0.6;
            pointer-events: none;
        }
        .kpi-title {
            font-size: 0.82rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: var(--ink-muted);
        }
        .kpi-value {
            font-size: 1.7rem;
            font-weight: 700;
            margin: 0.35rem 0 0.2rem 0;
        }
        .kpi-delta {
            font-size: 0.9rem;
            font-weight: 600;
        }
        .kpi-delta.up {
            color: #7ee787;
        }
        .kpi-delta.down {
            color: #ff8e8e;
        }
        .kpi-delta.flat {
            color: #c9d6ff;
        }
        .kpi-foot {
            font-size: 0.8rem;
            color: var(--ink-muted);
            margin-top: 0.3rem;
        }
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.8rem;
            margin-top: 0.75rem;
        }
        .summary-box {
            background: rgba(83, 82, 117, 0.45);
            border: 1px solid rgba(83, 82, 117, 0.6);
            border-radius: 14px;
            padding: 0.9rem 1rem;
        }
        .summary-label {
            color: #9fb1cb;
            font-size: 0.82rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }
        .summary-value {
            color: #f6f8fc;
            font-size: 1.15rem;
            font-weight: 700;
            margin-top: 0.2rem;
        }
        .insight-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 1rem;
            margin-top: 1rem;
        }
        .insight-card {
            background: rgba(80, 58, 85, 0.78);
            border: 1px solid rgba(52, 139, 168, 0.3);
            border-radius: 16px;
            padding: 1rem 1.1rem;
        }
        .insight-title {
            font-size: 0.95rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--ink-muted);
            margin-bottom: 0.4rem;
        }
        .insight-list {
            margin: 0.2rem 0 0 0;
            padding-left: 1rem;
            color: #d9e2f2;
        }
        .insight-list li {
            margin-bottom: 0.35rem;
        }
        .badge {
            display: inline-block;
            padding: 0.2rem 0.6rem;
            border-radius: 999px;
            font-size: 0.78rem;
            background: rgba(52, 139, 168, 0.22);
            color: #e2f3f8;
            border: 1px solid rgba(52, 139, 168, 0.4);
        }
        @keyframes fadeUp {
            from {
                opacity: 0;
                transform: translateY(12px);
            }
            to {
                opacity: 1;
                transform: translateY(0px);
            }
        }
        @media (max-width: 1100px) {
            .kpi-grid, .insight-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }
        @media (max-width: 720px) {
            .kpi-grid, .insight-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
    """,
    unsafe_allow_html=True,
)


def _coerce_timestamp(value: Any) -> str | None:
    if value is None:
        return datetime.now(timezone.utc).isoformat()

    try:
        if bool(pd.isna(value)):
            return datetime.now(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None

    try:
        parsed = pd.to_datetime(value, errors="coerce", utc=True)
    except (TypeError, ValueError):
        return None

    if pd.isna(parsed):
        return None
    return parsed.isoformat()


def _reason_code_success(reason_code: Any) -> bool:
    is_failure = getattr(reason_code, "is_failure", None)
    if isinstance(is_failure, bool):
        return not is_failure

    try:
        return int(reason_code) == 0
    except (TypeError, ValueError):
        return str(reason_code).lower() in {"0", "success"}


def _new_mqtt_client() -> mqtt.Client:
    callback_versions = getattr(mqtt, "CallbackAPIVersion", None)
    if callback_versions is not None:
        try:
            return mqtt.Client(callback_api_version=callback_versions.VERSION2)
        except (AttributeError, TypeError):
            pass
    return mqtt.Client()


class SensorStore:
    def __init__(self, data_file: Path, max_history: int) -> None:
        self.data_file = data_file
        self.history = deque(maxlen=max_history)
        self.lock = Lock()
        self.client: mqtt.Client | None = None
        self.connected = False
        self.last_error: str | None = None
        self.last_seen: str | None = None
        self._seen_samples: set[tuple[str, float, float]] = set()
        self._data_file_signature: tuple[int, int] | None = None
        self._load_seed_data()

    def _file_signature(self) -> tuple[int, int] | None:
        if not self.data_file.exists():
            return None
        try:
            stat = self.data_file.stat()
        except OSError:
            return None
        return stat.st_mtime_ns, stat.st_size

    @staticmethod
    def _sample_key(sample: dict) -> tuple[str, float, float]:
        return (
            str(sample["timestamp"]),
            round(float(sample["temp"]), 6),
            round(float(sample["hum"]), 6),
        )

    def _append_sample_in_memory(self, sample: dict) -> bool:
        sample_key = self._sample_key(sample)
        if sample_key in self._seen_samples:
            return False

        self.history.append(sample)
        self._seen_samples.add(sample_key)
        self.last_seen = sample["timestamp"]
        return True

    def _load_seed_data(self) -> None:
        if not self.data_file.exists():
            return

        try:
            seed_df = pd.read_csv(self.data_file)
        except Exception as exc:  # pragma: no cover - dashboard recovery path
            self.last_error = f"Gagal membaca {self.data_file.name}: {exc}"
            return

        if seed_df.empty:
            self._data_file_signature = self._file_signature()
            return

        for _, row in seed_df.iterrows():
            sample = self._normalize_sample(row.to_dict())
            if sample is not None:
                self._append_sample_in_memory(sample)

        self._data_file_signature = self._file_signature()

    def refresh_from_disk(self) -> None:
        """Sinkronkan ulang cache in-memory jika CSV berubah di luar MQTT callback."""
        signature = self._file_signature()
        if signature is None or signature == self._data_file_signature:
            return

        try:
            disk_df = pd.read_csv(self.data_file)
        except Exception as exc:  # pragma: no cover - dashboard recovery path
            with self.lock:
                self.last_error = f"Gagal membaca ulang {self.data_file.name}: {exc}"
            return

        if disk_df.empty:
            with self.lock:
                self._data_file_signature = signature
            return

        normalized_samples = []
        for _, row in disk_df.iterrows():
            sample = self._normalize_sample(row.to_dict())
            if sample is not None:
                normalized_samples.append(sample)

        with self.lock:
            for sample in normalized_samples:
                self._append_sample_in_memory(sample)
            self._data_file_signature = signature

    def _normalize_sample(self, payload: dict) -> dict | None:
        try:
            # Ubah "temp" menjadi "temperature" dan "hum" menjadi "humidity"
            temp = float(payload["temperature"])
            hum = float(payload["humidity"])
            gas = float(payload.get("gas", 0.0))
            buzzer = str(payload.get("buzzer", "OFF"))
        except (KeyError, TypeError, ValueError):
            return None

        if not np.isfinite(temp) or not np.isfinite(hum) or not 0 <= hum <= 100:
            return None

        timestamp = _coerce_timestamp(payload.get("timestamp") or payload.get("time"))
        if timestamp is None:
            return None

        return {
            "timestamp": timestamp,
            "temp": temp,
            "hum": hum,
            "gas": gas,
            "buzzer": buzzer,
        }

    def _append_to_disk(self, sample: dict) -> None:
        sample_df = pd.DataFrame([sample])
        sample_df.to_csv(
            self.data_file,
            mode="a",
            index=False,
            header=not self.data_file.exists() or self.data_file.stat().st_size == 0,
        )
        self._data_file_signature = self._file_signature()

    def add_sample(self, payload: dict) -> None:
        sample = self._normalize_sample(payload)
        if sample is None:
            return

        with self.lock:
            added = self._append_sample_in_memory(sample)
            if not added:
                return
            try:
                self._append_to_disk(sample)
            except Exception as exc:  # pragma: no cover - dashboard recovery path
                self.last_error = f"Gagal menulis {self.data_file.name}: {exc}"

    def snapshot(self) -> pd.DataFrame:
        self.refresh_from_disk()

        with self.lock:
            rows = list(self.history)

        if not rows:
            return pd.DataFrame(columns=["timestamp", "temp", "hum", "gas", "buzzer"])

        frame = pd.DataFrame(rows)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
        frame["temp"] = pd.to_numeric(frame["temp"], errors="coerce")
        frame["hum"] = pd.to_numeric(frame["hum"], errors="coerce")
        frame["gas"] = pd.to_numeric(frame["gas"], errors="coerce")
        # buzzer remains as is (string)
        frame = frame.dropna(subset=["timestamp", "temp", "hum", "gas"])
        frame = frame.sort_values("timestamp").reset_index(drop=True)
        return frame

    def ensure_connected(self) -> None:
        if self.client is not None:
            return

        try:
            client = _new_mqtt_client()
            if hasattr(client, "reconnect_delay_set"):
                client.reconnect_delay_set(min_delay=1, max_delay=30)

            def on_connect(client_obj, userdata, flags, reason_code, properties=None):
                del userdata, flags, properties
                if _reason_code_success(reason_code):
                    client_obj.subscribe(MQTT_TOPIC)
                    with self.lock:
                        self.connected = True
                        self.last_error = None
                else:
                    with self.lock:
                        self.connected = False
                        self.last_error = f"MQTT menolak koneksi: {reason_code}"

            def on_message(client_obj, userdata, msg):
                del client_obj, userdata
                try:
                    payload = json.loads(msg.payload.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    with self.lock:
                        self.last_error = f"Payload MQTT tidak valid: {exc}"
                    return

                if not isinstance(payload, dict):
                    with self.lock:
                        self.last_error = "Payload MQTT harus berupa objek JSON."
                    return

                self.add_sample(payload)

            def on_disconnect(client_obj, userdata, *args, **kwargs):
                del client_obj, userdata, args, kwargs
                with self.lock:
                    self.connected = False

            client.on_connect = on_connect
            client.on_message = on_message
            client.on_disconnect = on_disconnect
            client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
            client.loop_start()
            with self.lock:
                self.client = client
                self.connected = False
                self.last_error = None
        except Exception as exc:  # pragma: no cover - depends on local broker availability
            with self.lock:
                self.client = None
                self.connected = False
                self.last_error = f"Tidak bisa terhubung ke MQTT {MQTT_HOST}:{MQTT_PORT} - {exc}"


@st.cache_resource
def get_store() -> SensorStore:
    return SensorStore(DATA_FILE, MAX_HISTORY)


def build_linear_forecast(series: pd.Series, steps: int) -> np.ndarray:
    numeric = pd.to_numeric(series, errors="coerce").dropna().to_numpy(dtype=float)
    if len(numeric) == 0:
        return np.array([])
    if len(numeric) == 1:
        return np.repeat(numeric[-1], steps)

    x = np.arange(len(numeric), dtype=float)
    slope, intercept = np.polyfit(x, numeric, 1)
    future_x = np.arange(len(numeric), len(numeric) + steps, dtype=float)
    return intercept + slope * future_x


def infer_interval(frame: pd.DataFrame) -> pd.Timedelta:
    if len(frame) < 2:
        return pd.Timedelta(minutes=1)

    diffs = frame["timestamp"].diff().dropna()
    if diffs.empty:
        return pd.Timedelta(minutes=1)

    median_diff = pd.to_timedelta(diffs.median())
    if pd.isna(median_diff) or median_diff <= pd.Timedelta(0):
        return pd.Timedelta(minutes=1)
    return median_diff


def forecast_frame(frame: pd.DataFrame, horizon: int) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["step", "timestamp", "temp", "hum"])

    interval = infer_interval(frame)
    steps = list(range(1, horizon + 1))
    future_times = [frame["timestamp"].iloc[-1] + interval * step for step in steps]
    temp_forecast = build_linear_forecast(frame["temp"], horizon)
    hum_forecast = np.clip(build_linear_forecast(frame["hum"], horizon), 0, 100)

    return pd.DataFrame(
        {
            "step": steps,
            "timestamp": future_times,
            "temp": temp_forecast,
            "hum": hum_forecast,
        }
    )


def format_timestamp(value: Any, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return "N/A"

    try:
        parsed = parsed.tz_convert(DISPLAY_TIMEZONE)
    except (TypeError, ValueError, KeyError):
        pass

    return parsed.strftime(fmt)


def format_metric(value: float | None, decimals: int = 2) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value:.{decimals}f}"


def format_delta(value: float | None, unit: str) -> tuple[str, str]:
    if value is None or pd.isna(value):
        return "", "flat"
    tone = "up" if value > 0 else "down" if value < 0 else "flat"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f} {unit}", tone


def compute_dew_point(temp: float, hum: float) -> float:
    hum_clamped = float(np.clip(hum, 0, 100))
    return temp - (100 - hum_clamped) / 5.0


def compute_trend(series: pd.Series, window: int = 20) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna().tail(window)
    if len(values) < 3:
        return 0.0
    x = np.arange(len(values), dtype=float)
    slope, _ = np.polyfit(x, values.to_numpy(dtype=float), 1)
    return float(slope)


def describe_trend(slope: float, threshold: float) -> str:
    if slope > threshold:
        return "naik"
    if slope < -threshold:
        return "turun"
    return "stabil"


def detect_outliers(
    series: pd.Series,
    z_thresh: float = OUTLIER_Z_THRESHOLD,
    min_abs_delta: float = 0.0,
    min_samples: int = MIN_OUTLIER_SAMPLES,
) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    valid_values = values.dropna()

    if len(valid_values) < min_samples:
        return pd.Series([False] * len(series), index=series.index)

    median = valid_values.median()
    abs_dev = (values - median).abs()
    valid_abs_dev = (valid_values - median).abs()

    if min_abs_delta > 0 and (valid_values.max() - valid_values.min()) < min_abs_delta:
        return pd.Series([False] * len(series), index=series.index)

    mad = float(np.median(valid_abs_dev))
    if mad > 0 and np.isfinite(mad):
        score = 0.6745 * (values - median) / mad
    else:
        q1 = valid_values.quantile(0.25)
        q3 = valid_values.quantile(0.75)
        iqr = float(q3 - q1)
        if iqr > 0 and np.isfinite(iqr):
            score = (values - median) / (iqr / 1.349)
        else:
            std = float(valid_values.std(ddof=0))
            if std <= 0 or not np.isfinite(std):
                return pd.Series([False] * len(series), index=series.index)
            score = (values - median) / std

    return (score.abs() > z_thresh) & (abs_dev >= min_abs_delta)


def format_age(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f} dtk"
    if seconds < 3600:
        return f"{seconds / 60:.1f} mnt"
    return f"{seconds / 3600:.1f} jam"


def style_chart(chart: alt.Chart | alt.LayerChart | alt.FacetChart) -> alt.Chart | alt.LayerChart | alt.FacetChart:
    return (
        chart.configure_axis(
            gridColor="rgba(255,255,255,0.14)",
            gridOpacity=0.4,
            labelColor="#e4edf9",
            titleColor="#e4edf9",
            tickColor="rgba(255,255,255,0.2)",
        )
        .configure_legend(labelColor="#d8e4f6", titleColor="#d8e4f6")
        .configure_view(strokeOpacity=0)
        .configure_range(category=["#348ba8", "#bce784", "#535275", "#503a55"])
    )


def build_metric_chart(melted: pd.DataFrame) -> alt.Chart | alt.LayerChart | alt.FacetChart:
    base = (
        alt.Chart(melted)
        .mark_line(point=True)
        .encode(
            x=alt.X("timestamp:T", title="Waktu"),
            y=alt.Y("value:Q", title="Nilai"),
            color=alt.Color("metric:N", title="Metrik"),
            tooltip=[alt.Tooltip("display_time:N", title=f"Waktu ({DISPLAY_TIMEZONE})"), "metric:N", alt.Tooltip("value:Q", format=".2f")],
        )
    )

    outlier_data = melted[melted["is_outlier"]]
    if outlier_data.empty:
        return base

    outliers = (
        alt.Chart(outlier_data)
        .mark_point(shape="triangle-up", size=130, filled=True, color="#ff8e8e")
        .encode(
            x=alt.X("timestamp:T", title="Waktu"),
            y=alt.Y("value:Q", title="Nilai"),
            tooltip=[alt.Tooltip("display_time:N", title=f"Waktu ({DISPLAY_TIMEZONE})"), "metric:N", alt.Tooltip("value:Q", format=".2f")],
        )
    )

    return alt.layer(base, outliers)


def _prepare_model_frame(frame: pd.DataFrame) -> pd.DataFrame:
    model_frame = frame.copy()
    model_frame["hour"] = model_frame["timestamp"].dt.hour.astype(float)
    model_frame["minute"] = model_frame["timestamp"].dt.minute.astype(float)
    model_frame["dayofweek"] = model_frame["timestamp"].dt.dayofweek.astype(float)

    for lag in range(1, LAG_WINDOW + 1):
        model_frame[f"temp_lag_{lag}"] = model_frame["temp"].shift(lag)
        model_frame[f"hum_lag_{lag}"] = model_frame["hum"].shift(lag)

    model_frame["temp_roll_mean_3"] = model_frame["temp"].rolling(3).mean()
    model_frame["hum_roll_mean_3"] = model_frame["hum"].rolling(3).mean()
    model_frame["temp_roll_std_3"] = model_frame["temp"].rolling(3).std()
    model_frame["hum_roll_std_3"] = model_frame["hum"].rolling(3).std()

    timestamp_delta = model_frame["timestamp"].diff().dt.total_seconds().fillna(0)
    model_frame["delta_seconds"] = timestamp_delta
    model_frame["hour_sin"] = np.sin(2 * np.pi * model_frame["hour"] / 24.0)
    model_frame["hour_cos"] = np.cos(2 * np.pi * model_frame["hour"] / 24.0)
    model_frame["dow_sin"] = np.sin(2 * np.pi * model_frame["dayofweek"] / 7.0)
    model_frame["dow_cos"] = np.cos(2 * np.pi * model_frame["dayofweek"] / 7.0)

    return model_frame


def _feature_columns() -> list[str]:
    return [
        "hour_sin",
        "hour_cos",
        "dow_sin",
        "dow_cos",
        "minute",
        "delta_seconds",
        *[f"temp_lag_{lag}" for lag in range(1, LAG_WINDOW + 1)],
        *[f"hum_lag_{lag}" for lag in range(1, LAG_WINDOW + 1)],
        "temp_roll_mean_3",
        "hum_roll_mean_3",
        "temp_roll_std_3",
        "hum_roll_std_3",
    ]


def _train_regressor(model_frame: pd.DataFrame, target: str) -> tuple[RandomForestRegressor | None, dict[str, float]]:
    feature_columns = _feature_columns()
    target_frame = model_frame.dropna(subset=feature_columns + [target]).copy()
    if len(target_frame) < MIN_TRAINING_SAMPLES:
        return None, {"mae": float("nan"), "r2": float("nan")}

    split_index = max(int(len(target_frame) * 0.8), MIN_TRAINING_SAMPLES - 1)
    train_frame = target_frame.iloc[:split_index]
    valid_frame = target_frame.iloc[split_index:]

    if valid_frame.empty:
        valid_frame = train_frame.tail(max(1, len(train_frame) // 4))
        train_frame = train_frame.iloc[: len(train_frame) - len(valid_frame)]

    if train_frame.empty or valid_frame.empty:
        return None, {"mae": float("nan"), "r2": float("nan")}

    model = RandomForestRegressor(
        n_estimators=240,
        max_depth=12,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(train_frame[feature_columns], train_frame[target])
    predictions = model.predict(valid_frame[feature_columns])

    metrics = {
        "mae": float(mean_absolute_error(valid_frame[target], predictions)),
        "r2": float(r2_score(valid_frame[target], predictions)) if len(valid_frame) >= 2 else float("nan"),
    }
    return model, metrics


def _make_feature_row(history_frame: pd.DataFrame, current_timestamp: pd.Timestamp, temp_value: float, hum_value: float) -> dict[str, float]:
    feature_row = {
        "timestamp": current_timestamp,
        "temp": temp_value,
        "hum": hum_value,
        "hour": float(current_timestamp.hour),
        "minute": float(current_timestamp.minute),
        "dayofweek": float(current_timestamp.dayofweek),
        "hour_sin": float(np.sin(2 * np.pi * current_timestamp.hour / 24.0)),
        "hour_cos": float(np.cos(2 * np.pi * current_timestamp.hour / 24.0)),
        "dow_sin": float(np.sin(2 * np.pi * current_timestamp.dayofweek / 7.0)),
        "dow_cos": float(np.cos(2 * np.pi * current_timestamp.dayofweek / 7.0)),
        "delta_seconds": float((current_timestamp - history_frame["timestamp"].iloc[-1]).total_seconds()) if len(history_frame) else 0.0,
    }

    for lag in range(1, LAG_WINDOW + 1):
        temp_lag_col = f"temp_lag_{lag}"
        hum_lag_col = f"hum_lag_{lag}"
        feature_row[temp_lag_col] = float(history_frame["temp"].iloc[-lag]) if len(history_frame) >= lag else temp_value
        feature_row[hum_lag_col] = float(history_frame["hum"].iloc[-lag]) if len(history_frame) >= lag else hum_value

    history_tail = history_frame.tail(3)
    feature_row["temp_roll_mean_3"] = float(history_tail["temp"].mean()) if not history_tail.empty else temp_value
    feature_row["hum_roll_mean_3"] = float(history_tail["hum"].mean()) if not history_tail.empty else hum_value
    feature_row["temp_roll_std_3"] = float(history_tail["temp"].std(ddof=0)) if len(history_tail) > 1 else 0.0
    feature_row["hum_roll_std_3"] = float(history_tail["hum"].std(ddof=0)) if len(history_tail) > 1 else 0.0

    return feature_row


def forecast_with_models(frame: pd.DataFrame, horizon: int) -> tuple[pd.DataFrame, dict[str, float], dict[str, float]]:
    if frame.empty:
        empty = pd.DataFrame(columns=["step", "timestamp", "temp", "hum"])
        return empty, {"mae": float("nan"), "r2": float("nan")}, {"mae": float("nan"), "r2": float("nan")}

    if len(frame) < MIN_TRAINING_SAMPLES:
        fallback = forecast_frame(frame, horizon)
        return fallback, {"mae": float("nan"), "r2": float("nan")}, {"mae": float("nan"), "r2": float("nan")}

    model_frame = _prepare_model_frame(frame)
    temp_model, temp_metrics = _train_regressor(model_frame, "temp")
    hum_model, hum_metrics = _train_regressor(model_frame, "hum")

    if temp_model is None or hum_model is None:
        fallback = forecast_frame(frame, horizon)
        return fallback, temp_metrics, hum_metrics

    interval = infer_interval(frame)
    history_buffer = frame.copy().reset_index(drop=True)
    predictions: list[dict[str, float]] = []

    for step_index in range(horizon):
        step_number = step_index + 1
        next_timestamp = history_buffer["timestamp"].iloc[-1] + interval
        provisional_temp = float(history_buffer["temp"].iloc[-1])
        provisional_hum = float(history_buffer["hum"].iloc[-1])
        feature_row = _make_feature_row(history_buffer, next_timestamp, provisional_temp, provisional_hum)
        feature_df = pd.DataFrame([feature_row])

        temp_pred = float(temp_model.predict(feature_df[_feature_columns()])[0])
        hum_pred = float(np.clip(hum_model.predict(feature_df[_feature_columns()])[0], 0, 100))

        predictions.append(
            {
                "step": step_number,
                "timestamp": next_timestamp,
                "temp": temp_pred,
                "hum": hum_pred,
            }
        )
        history_buffer = pd.concat(
            [history_buffer, pd.DataFrame([{"timestamp": next_timestamp, "temp": temp_pred, "hum": hum_pred}])],
            ignore_index=True,
        )

    return pd.DataFrame(predictions), temp_metrics, hum_metrics


def main() -> None:
    store = get_store()
    store.ensure_connected()

    st.markdown(
        """
        <div class="hero-card">
            <p class="hero-title">IoT ESP32 Dashboard</p>
            <p class="hero-subtitle">Monitoring realtime suhu dan kelembaban dengan visualisasi, histori, dan prediksi machine learning berbasis scikit-learn.</p>
            <span class="pill">MQTT</span>
            <span class="pill">Streamlit</span>
            <span class="pill">ML Forecast</span>
            <span class="pill">Random Forest</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("Kontrol")
        auto_refresh = st.toggle("Auto refresh", value=True)
        refresh_seconds = st.slider("Interval refresh (detik)", 3, 30, 5)
        forecast_steps = st.slider("Langkah prediksi", 1, 12, 5)
        show_raw_rows = st.slider("Baris data mentah", 10, 200, 50, 10)

        st.caption("Sumber data")
        st.write(f"Broker: `{MQTT_HOST}:{MQTT_PORT}`")
        st.write(f"Topik: `{MQTT_TOPIC}`")
        st.write(f"File: `{DATA_FILE.name}`")

        if store.connected:
            st.success("MQTT tersambung")
        else:
            st.warning("MQTT belum tersambung")

        if store.last_error:
            st.error(store.last_error)

        st.divider()
        st.caption("Status model")
        st.write(f"Min sampel training: {MIN_TRAINING_SAMPLES}")
        st.write(f"Lag window: {LAG_WINDOW}")


    if auto_refresh:
        import time
        time.sleep(refresh_seconds)
        st.rerun()


    frame = store.snapshot()

    if frame.empty:
        st.info("Menunggu data sensor dari MQTT. Dashboard akan otomatis terisi setelah payload pertama masuk.")
        st.stop()


    latest = frame.iloc[-1]
    previous = frame.iloc[-2] if len(frame) > 1 else None
    prediction, temp_metrics, hum_metrics = forecast_with_models(frame, forecast_steps)

    temp_delta = latest["temp"] - previous["temp"] if previous is not None else None
    hum_delta = latest["hum"] - previous["hum"] if previous is not None else None
    temp_delta_text, temp_delta_tone = format_delta(temp_delta, "°C")
    hum_delta_text, hum_delta_tone = format_delta(hum_delta, "%")
    dew_point = compute_dew_point(float(latest["temp"]), float(latest["hum"]))
    interval = infer_interval(frame)
    last_timestamp = pd.to_datetime(latest["timestamp"], utc=True)
    now_timestamp = pd.Timestamp.now(tz=timezone.utc)
    age_seconds = max((now_timestamp - last_timestamp).total_seconds(), 0.0)
    fresh_limit = interval.total_seconds() * 3
    freshness_label = "Segar" if age_seconds <= fresh_limit else "Terlambat"
    trend_temp = describe_trend(compute_trend(frame["temp"]), 0.02)
    trend_hum = describe_trend(compute_trend(frame["hum"]), 0.05)
    temp_outlier_mask = detect_outliers(frame["temp"], min_abs_delta=TEMP_OUTLIER_MIN_DELTA)
    hum_outlier_mask = detect_outliers(frame["hum"], min_abs_delta=HUM_OUTLIER_MIN_DELTA)
    temp_outliers = int(temp_outlier_mask.tail(50).sum())
    hum_outliers = int(hum_outlier_mask.tail(50).sum())
    frame_with_flags = frame.assign(temp_outlier=temp_outlier_mask, hum_outlier=hum_outlier_mask)
    melted_metrics = frame_with_flags.melt(
        id_vars=["timestamp", "temp_outlier", "hum_outlier"],
        value_vars=["temp", "hum"],
        var_name="metric",
        value_name="value",
    )
    melted_metrics["is_outlier"] = (
        ((melted_metrics["metric"] == "temp") & melted_metrics["temp_outlier"])
        | ((melted_metrics["metric"] == "hum") & melted_metrics["hum_outlier"])
    )
    melted_metrics["display_time"] = melted_metrics["timestamp"].map(format_timestamp)
    outlier_rows = frame_with_flags[frame_with_flags["temp_outlier"] | frame_with_flags["hum_outlier"]].copy()
    latest_outlier = bool(frame_with_flags.iloc[-1]["temp_outlier"] or frame_with_flags.iloc[-1]["hum_outlier"])
    latest_outlier_types = ", ".join(
        label
        for label, flag in (
            ("Suhu", frame_with_flags.iloc[-1]["temp_outlier"]),
            ("Kelembaban", frame_with_flags.iloc[-1]["hum_outlier"]),
        )
        if flag
    )
    temp_volatility = format_metric(frame["temp"].tail(24).std())
    hum_volatility = format_metric(frame["hum"].tail(24).std())
    temp_mae = format_metric(temp_metrics["mae"])
    temp_r2 = format_metric(temp_metrics["r2"])
    hum_mae = format_metric(hum_metrics["mae"])
    hum_r2 = format_metric(hum_metrics["r2"])

    st.markdown(
        f"""
        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-title">Suhu sekarang</div>
                <div class="kpi-value">{latest['temp']:.2f} °C</div>
                <div class="kpi-delta {temp_delta_tone}">{temp_delta_text or '&nbsp;'}</div>
                <div class="kpi-foot">Tren: {trend_temp}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Kelembaban sekarang</div>
                <div class="kpi-value">{latest['hum']:.2f} %</div>
                <div class="kpi-delta {hum_delta_tone}">{hum_delta_text or '&nbsp;'}</div>
                <div class="kpi-foot">Tren: {trend_hum}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Gas</div>
                <div class="kpi-value">{latest['gas']:.0f}</div>
                <div class="kpi-foot">Status: {"Normal" if latest['gas'] < 2000 else "Bahaya"}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Buzzer</div>
                <div class="kpi-value">{latest['buzzer']}</div>
                <div class="kpi-foot">Status terkini</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Dew point</div>
                <div class="kpi-value">{dew_point:.2f} °C</div>
                <div class="kpi-foot">Kenyamanan: {"Nyaman" if 20 <= latest['temp'] <= 27 and 40 <= latest['hum'] <= 60 else "Kurang nyaman"}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Status data</div>
                <div class="kpi-value">{freshness_label}</div>
                <div class="kpi-foot">Terakhir: {format_age(age_seconds)} | Interval: {format_age(interval.total_seconds())}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if latest_outlier:
        st.warning(
            f"Outlier terdeteksi pada sampel terbaru ({format_timestamp(latest['timestamp'], '%H:%M:%S')}): {latest_outlier_types}.",
            icon="⚠️",
        )

    st.markdown(
        f"""
        <div class="summary-grid">
            <div class="summary-box">
                <div class="summary-label">Model suhu</div>
                <div class="summary-value">MAE: {temp_mae} | R²: {temp_r2}</div>
            </div>
            <div class="summary-box">
                <div class="summary-label">Model kelembaban</div>
                <div class="summary-value">MAE: {hum_mae} | R²: {hum_r2}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="insight-grid">
            <div class="insight-card">
                <div class="insight-title">Insight cepat</div>
                <ul class="insight-list">
                    <li>Tren suhu {trend_temp}, tren kelembaban {trend_hum}.</li>
                    <li>Volatilitas suhu {temp_volatility} °C, kelembaban {hum_volatility} % (24 sampel terakhir).</li>
                    <li>Data terakhir masuk {format_age(age_seconds)} yang lalu.</li>
                </ul>
            </div>
            <div class="insight-card">
                <div class="insight-title">Kualitas data</div>
                <ul class="insight-list">
                    <li>Outlier suhu (50 sampel terakhir): {temp_outliers} titik.</li>
                    <li>Outlier kelembaban (50 sampel terakhir): {hum_outliers} titik.</li>
                    <li>Model aktif: <span class="badge">{"Random Forest" if len(frame) >= MIN_TRAINING_SAMPLES else "Fallback linear"}</span></li>
                </ul>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


    tab_ringkasan, tab_prediksi, tab_anomali, tab_data, tab_fitur = st.tabs(
        ["Ringkasan", "Prediksi", "Anomali", "Data Mentah", "Fitur"]
    )

    with tab_ringkasan:
        left, right = st.columns([1.3, 1])

        with left:
            chart = build_metric_chart(melted_metrics).properties(height=320)
            st.altair_chart(style_chart(chart), use_container_width=True)
            st.caption("Segitiga merah menandai outlier yang terdeteksi.")

        with right:
            st.subheader("Ringkasan data")
            summary_cols = st.columns(2)
            with summary_cols[0]:
                st.metric("Rata-rata suhu", f"{frame['temp'].mean():.2f} °C")
                st.metric("Suhu minimum", f"{frame['temp'].min():.2f} °C")
                st.metric("Suhu maksimum", f"{frame['temp'].max():.2f} °C")
            with summary_cols[1]:
                st.metric("Rata-rata kelembaban", f"{frame['hum'].mean():.2f} %")
                st.metric("Kelembaban minimum", f"{frame['hum'].min():.2f} %")
                st.metric("Kelembaban maksimum", f"{frame['hum'].max():.2f} %")

            st.caption("Distribusi sederhana")
            st.bar_chart(frame.set_index("timestamp")[["temp", "hum"]].tail(24))


    with tab_prediksi:
        if prediction.empty:
            st.warning("Belum cukup data untuk membuat prediksi.")
        else:
            prediction = prediction.copy()
            if "step" not in prediction.columns:
                prediction.insert(0, "step", range(1, len(prediction) + 1))
            prediction["step"] = pd.to_numeric(prediction["step"], errors="coerce").fillna(0).astype(int)
            prediction["step_label"] = prediction["step"].map(lambda value: f"Langkah {value}")
            prediction["display_time"] = prediction["timestamp"].map(format_timestamp)

            forecast_start_text = format_timestamp(last_timestamp)
            forecast_end_text = format_timestamp(prediction["timestamp"].iloc[-1])
            forecast_end_clock = format_timestamp(prediction["timestamp"].iloc[-1], "%H:%M:%S")
            final_temp = float(prediction["temp"].iloc[-1])
            final_hum = float(prediction["hum"].iloc[-1])

            st.caption(
                f"Prediksi {len(prediction)} langkah dari data terakhir {forecast_start_text} sampai "
                f"{forecast_end_text}. Interval data terdeteksi {format_age(interval.total_seconds())}."
            )
            summary_prediction_cols = st.columns(3)
            with summary_prediction_cols[0]:
                st.metric("Mulai prediksi", format_timestamp(last_timestamp, "%H:%M:%S"))
            with summary_prediction_cols[1]:
                st.metric(f"Selesai langkah {len(prediction)}", forecast_end_clock)
            with summary_prediction_cols[2]:
                st.metric("Prediksi akhir", f"{final_temp:.2f} °C | {final_hum:.2f} %")

            st.info(
                f"Artinya, jika sekarang data terakhir berada di {format_timestamp(last_timestamp, '%H:%M:%S')}, "
                f"maka langkah ke-{len(prediction)} berakhir pada {forecast_end_clock} dengan prediksi "
                f"suhu {final_temp:.2f} °C dan kelembaban {final_hum:.2f} %.",
                icon="ℹ️",
            )

            pred_left, pred_right = st.columns(2)
            actual_limit = max(50, len(prediction) * 4)
            prediction_boundary = pd.DataFrame({"timestamp": [last_timestamp]})

            with pred_left:
                temp_actual = frame[["timestamp", "temp"]].tail(actual_limit).assign(
                    kind="Aktual",
                    step_label="Aktual",
                )
                temp_actual["display_time"] = temp_actual["timestamp"].map(format_timestamp)
                temp_pred = prediction[["timestamp", "temp", "step_label", "display_time"]].assign(kind="Prediksi")
                temp_compare = pd.concat([temp_actual, temp_pred], ignore_index=True)
                temp_final_annotation = prediction.tail(1).assign(
                    label=lambda data: data["step_label"] + " • " + data["timestamp"].map(lambda value: format_timestamp(value, "%H:%M"))
                )

                temp_line = (
                    alt.Chart(temp_compare)
                    .mark_line(point=True)
                    .encode(
                        x=alt.X("timestamp:T", title="Waktu"),
                        y=alt.Y("temp:Q", title="Suhu (°C)"),
                        color=alt.Color("kind:N", title="Mode"),
                        strokeDash=alt.StrokeDash("kind:N", title="Mode"),
                        tooltip=[
                            alt.Tooltip("display_time:N", title=f"Waktu ({DISPLAY_TIMEZONE})"),
                            alt.Tooltip("kind:N", title="Mode"),
                            alt.Tooltip("step_label:N", title="Langkah"),
                            alt.Tooltip("temp:Q", title="Suhu (°C)", format=".2f"),
                        ],
                    )
                )
                temp_rule = alt.Chart(prediction_boundary).mark_rule(strokeDash=[4, 4], opacity=0.7).encode(
                    x=alt.X("timestamp:T")
                )
                temp_label = (
                    alt.Chart(temp_final_annotation)
                    .mark_text(align="left", dx=8, dy=-8, fontSize=12)
                    .encode(x=alt.X("timestamp:T"), y=alt.Y("temp:Q"), text="label:N")
                )
                temp_chart = alt.layer(temp_line, temp_rule, temp_label).properties(height=320)
                st.altair_chart(style_chart(temp_chart), use_container_width=True)

            with pred_right:
                hum_actual = frame[["timestamp", "hum"]].tail(actual_limit).assign(
                    kind="Aktual",
                    step_label="Aktual",
                )
                hum_actual["display_time"] = hum_actual["timestamp"].map(format_timestamp)
                hum_pred = prediction[["timestamp", "hum", "step_label", "display_time"]].assign(kind="Prediksi")
                hum_compare = pd.concat([hum_actual, hum_pred], ignore_index=True)
                hum_final_annotation = prediction.tail(1).assign(
                    label=lambda data: data["step_label"] + " • " + data["timestamp"].map(lambda value: format_timestamp(value, "%H:%M"))
                )

                hum_line = (
                    alt.Chart(hum_compare)
                    .mark_line(point=True)
                    .encode(
                        x=alt.X("timestamp:T", title="Waktu"),
                        y=alt.Y("hum:Q", title="Kelembaban (%)"),
                        color=alt.Color("kind:N", title="Mode"),
                        strokeDash=alt.StrokeDash("kind:N", title="Mode"),
                        tooltip=[
                            alt.Tooltip("display_time:N", title=f"Waktu ({DISPLAY_TIMEZONE})"),
                            alt.Tooltip("kind:N", title="Mode"),
                            alt.Tooltip("step_label:N", title="Langkah"),
                            alt.Tooltip("hum:Q", title="Kelembaban (%)", format=".2f"),
                        ],
                    )
                )
                hum_rule = alt.Chart(prediction_boundary).mark_rule(strokeDash=[4, 4], opacity=0.7).encode(
                    x=alt.X("timestamp:T")
                )
                hum_label = (
                    alt.Chart(hum_final_annotation)
                    .mark_text(align="left", dx=8, dy=-8, fontSize=12)
                    .encode(x=alt.X("timestamp:T"), y=alt.Y("hum:Q"), text="label:N")
                )
                hum_chart = alt.layer(hum_line, hum_rule, hum_label).properties(height=320)
                st.altair_chart(style_chart(hum_chart), use_container_width=True)

            st.subheader("Hasil prediksi")
            prediction_view = pd.DataFrame(
                {
                    "Langkah": prediction["step"].astype(int),
                    f"Waktu ({DISPLAY_TIMEZONE})": prediction["timestamp"].map(format_timestamp),
                    "Suhu prediksi (°C)": prediction["temp"].round(2),
                    "Kelembaban prediksi (%)": prediction["hum"].round(2),
                }
            )
            st.dataframe(
                prediction_view,
                use_container_width=True,
                hide_index=True,
            )


    with tab_anomali:
        st.subheader("Anomali sensor")
        st.caption(f"Segitiga merah hanya muncul jika deviasi melewati ambang robust dan perubahan minimum sensor (suhu ≥ {TEMP_OUTLIER_MIN_DELTA:g} °C, kelembaban ≥ {HUM_OUTLIER_MIN_DELTA:g} %).")

        anomaly_chart = build_metric_chart(melted_metrics).properties(height=360)
        st.altair_chart(style_chart(anomaly_chart), use_container_width=True)

        if outlier_rows.empty:
            st.info("Belum ada outlier terdeteksi pada data saat ini.")
        else:
            outlier_view = outlier_rows.copy()
            outlier_view["timestamp"] = outlier_view["timestamp"].map(format_timestamp)
            outlier_view["temp"] = outlier_view["temp"].round(2)
            outlier_view["hum"] = outlier_view["hum"].round(2)
            outlier_view["tipe"] = np.select(
                [
                    outlier_view["temp_outlier"] & outlier_view["hum_outlier"],
                    outlier_view["temp_outlier"],
                    outlier_view["hum_outlier"],
                ],
                ["Suhu + Kelembaban", "Suhu", "Kelembaban"],
                default="",
            )
            st.dataframe(
                outlier_view[["timestamp", "temp", "hum", "tipe"]].tail(200),
                use_container_width=True,
                hide_index=True,
            )


    with tab_data:
        st.subheader("Data terbaru")
        raw_view = frame.tail(show_raw_rows).copy()
        raw_view["timestamp"] = raw_view["timestamp"].map(format_timestamp)
        raw_view["temp"] = raw_view["temp"].round(2)
        raw_view["hum"] = raw_view["hum"].round(2)
        st.dataframe(raw_view, use_container_width=True, hide_index=True)

        csv_bytes = frame.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Unduh CSV",
            data=csv_bytes,
            file_name=DATA_FILE.name,
            mime="text/csv",
        )

    with tab_fitur:
        st.subheader("Fitur yang tersedia")
        st.markdown(
            """
            - Realtime MQTT ingest untuk suhu dan kelembaban.
            - Penyimpanan otomatis ke CSV dan download langsung dari dashboard.
            - KPI premium: tren, dew point, dan status data terbaru.
            - Prediksi ML dengan Random Forest plus fallback linear jika data belum cukup.
            - Monitoring kualitas data (outlier, volatilitas, dan freshness).
            - Visualisasi interaktif: ringkasan, prediksi, dan data mentah.
            """
        )
        st.caption("Semua fitur di atas berjalan lokal tanpa konfigurasi tambahan selain broker MQTT.")


if __name__ == "__main__":
    main()
