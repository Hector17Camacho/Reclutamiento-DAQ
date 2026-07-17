#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Análisis de Telemetría — Formula SAE (PyQt5 + Matplotlib)
Dashboard profesional con diagrama G-G, diagnóstico automático, detección de anomalías y reportes.
"""

import sys
import os
import numpy as np
import pandas as pd
from scipy import signal
from scipy.stats import median_abs_deviation
from scipy.spatial import ConvexHull
from scipy.interpolate import splprep, splev
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
import traceback
import faulthandler
import logging

# Registro persistente para errores de Python y fallos nativos.
LOG_FILE = Path(__file__).with_name("f1_telemetry_crash.log")
logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.ERROR,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

_FAULT_LOG_HANDLE = open(LOG_FILE, "a", encoding="utf-8")
faulthandler.enable(_FAULT_LOG_HANDLE)

def global_exception_handler(exc_type, exc_value, exc_traceback):
    """Evita que una excepción no controlada cierre PyQt silenciosamente."""
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    logging.error("Excepción no controlada:\n%s", msg)
    print(msg, file=sys.stderr)

    app = QApplication.instance()
    if app is not None:
        try:
            QMessageBox.critical(
                None,
                "Error inesperado",
                "Ocurrió un error y fue registrado en:\n"
                f"{LOG_FILE}\n\n"
                "La aplicación intentará permanecer abierta."
            )
        except Exception:
            pass

sys.excepthook = global_exception_handler

# PyQt5
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QTabWidget, QTabBar, QComboBox, QPushButton,
    QTextEdit, QLineEdit, QSlider, QProgressBar, QSizePolicy,
    QSplitter, QMessageBox, QFileDialog, QTableWidget, QTableWidgetItem,
    QGroupBox, QFormLayout, QSpinBox, QDoubleSpinBox, QCheckBox,
    QHeaderView, QProgressDialog, QGridLayout, QDialog
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QPainter, QPen, QBrush, QColor, QFont, QLinearGradient

# Matplotlib
import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

# =============================================================================
# PALETA DE COLORES (estilo oscuro profesional)
# =============================================================================
DARK_PALETTE = {
    "bg0":     "#0A0E17",
    "bg1":     "#111827",
    "bg2":     "#1F2937",
    "bg3":     "#374151",
    "cyan":    "#00E5FF",
    "blue":    "#3B82F6",
    "gold":    "#FFB703",
    "red":     "#FF4D4D",
    "green":   "#10B981",
    "text_w":  "#F3F4F6",
    "text_g":  "#9CA3AF",
    "border":  "#374151",
    "critical": "#FF3333"
}

CURRENT_PALETTE = DARK_PALETTE

def C(key):
    """Devuelve color seguro desde la paleta actual."""
    return CURRENT_PALETTE.get(key, CURRENT_PALETTE.get("cyan", "#00E5FF"))

FONT = "Segoe UI, Roboto, sans-serif"

# =============================================================================
# MODELO DE EVENTOS
# =============================================================================
_event_counter = 0
def generate_event_id():
    global _event_counter
    _event_counter += 1
    return f"EVT_{_event_counter:04d}"

@dataclass
class Event:
    id: str = field(default_factory=generate_event_id)
    category: str = "Unknown"
    type: str = "Unknown"
    severity: str = "Info"
    channels: List[str] = field(default_factory=list)
    start_sample: int = 0
    end_sample: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    duration: float = 0.0
    metrics: Dict[str, float] = field(default_factory=dict)
    probable_cause: str = ""
    recommended_action: str = ""
    description: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "id": self.id,
            "category": self.category,
            "type": self.type,
            "severity": self.severity,
            "channels": ", ".join(self.channels),
            "start_sample": self.start_sample,
            "end_sample": self.end_sample,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "metrics": str(self.metrics),
            "probable_cause": self.probable_cause,
            "recommended_action": self.recommended_action,
            "description": self.description,
        }

class EventRegistry:
    def __init__(self):
        self._events = []

    def add_event(self, event):
        self._events.append(event)

    def add_events(self, events):
        self._events.extend(events)

    def clear(self):
        self._events.clear()

    @property
    def events(self):
        return self._events.copy()

    def filter(self, category=None, severity=None, channel=None):
        result = self._events
        if category:
            result = [e for e in result if e.category.lower() == category.lower()]
        if severity:
            result = [e for e in result if e.severity.lower() == severity.lower()]
        if channel:
            result = [e for e in result if channel.lower() in [c.lower() for c in e.channels]]
        return result

    def to_dataframe(self):
        if not self._events:
            return pd.DataFrame()
        return pd.DataFrame([e.to_dict() for e in self._events])

    def get_summary(self):
        if not self._events:
            return {"total": 0, "by_category": {}, "by_severity": {}, "critical_count": 0}
        df = self.to_dataframe()
        return {
            "total": len(df),
            "by_category": df["category"].value_counts().to_dict(),
            "by_severity": df["severity"].value_counts().to_dict(),
            "critical_count": len(df[df["severity"] == "Crítico"]),
        }

    def __len__(self):
        return len(self._events)

# =============================================================================
# FUNCIONES DE PROCESAMIENTO (sin cambios en lógica, textos traducidos)
# =============================================================================
def design_filter(filter_type, order, cutoff, fs, **kwargs):
    nyquist = fs / 2.0
    if cutoff >= nyquist:
        raise ValueError(f"Cutoff {cutoff} Hz must be < Nyquist {nyquist} Hz")
    if order < 1:
        raise ValueError("Order must be at least 1")
    if filter_type == "butter":
        sos = signal.butter(order, cutoff, fs=fs, btype='low', output='sos')
    elif filter_type == "cheby1":
        ripple = kwargs.get('ripple', 0.5)
        sos = signal.cheby1(order, ripple, cutoff, fs=fs, btype='low', output='sos')
    elif filter_type == "cheby2":
        atten = kwargs.get('attenuation', 40)
        sos = signal.cheby2(order, atten, cutoff, fs=fs, btype='low', output='sos')
    elif filter_type == "ellip":
        ripple = kwargs.get('ripple', 0.5)
        atten = kwargs.get('attenuation', 40)
        sos = signal.ellip(order, ripple, atten, cutoff, fs=fs, btype='low', output='sos')
    else:
        raise ValueError(f"Unsupported filter type: {filter_type}")
    return sos

def apply_filter(signal_data, sos):
    if np.any(np.isnan(signal_data)):
        mask = np.isnan(signal_data)
        x = np.arange(len(signal_data))
        signal_data_interp = np.interp(x, x[~mask], signal_data[~mask])
    else:
        signal_data_interp = signal_data
    filtered = signal.sosfiltfilt(sos, signal_data_interp)
    if np.any(np.isnan(signal_data)):
        filtered[mask] = np.nan
    return filtered

def compute_psd(signal_data, fs, nperseg=256):
    s = signal_data[~np.isnan(signal_data)]
    if len(s) < nperseg:
        return None, None
    f, Pxx = signal.welch(s, fs=fs, nperseg=nperseg, scaling='density')
    return f, Pxx

def compute_high_freq_energy(signal_data, fs, high_freq_threshold):
    f, Pxx = compute_psd(signal_data, fs)
    if f is None or len(f) == 0:
        return np.nan, np.nan, np.nan
    total_energy = np.trapezoid(Pxx, f)
    high_idx = f >= high_freq_threshold
    high_energy = np.trapezoid(Pxx[high_idx], f[high_idx]) if np.any(high_idx) else 0.0
    ratio = high_energy / total_energy if total_energy > 0 else 0.0
    return total_energy, high_energy, ratio

def compute_g_combined(ax, ay, units="G", g_conversion=9.80665):
    if units.lower() == "m/s2":
        ax = ax / g_conversion
        ay = ay / g_conversion
    return np.sqrt(ax**2 + ay**2)

def compute_asymmetry(data_left, data_right, percentile=95):
    if len(data_left) == 0 or len(data_right) == 0:
        return 0.0, 0.0, 0.0
    p_left = np.percentile(np.abs(data_left), percentile)
    p_right = np.percentile(np.abs(data_right), percentile)
    asym = (p_left - p_right) / max(p_left, p_right) if max(p_left, p_right) > 0 else 0.0
    return p_left, p_right, asym

# Traducciones para eventos
CATEGORY_ES = {
    "Data Integrity": "Integridad de datos",
    "Sensor Integrity": "Integridad del sensor",
    "Signal Quality": "Calidad de señal",
    "Plausibility": "Plausibilidad",
    "Vehicle Dynamics": "Dinámica vehicular",
}

TYPE_ES = {
    "NaN Values": "Pérdida de datos",
    "Flatline / Stuck Sensor": "Sensor bloqueado / señal constante",
    "High Saturation": "Saturación superior",
    "Low Saturation": "Saturación inferior",
    "Spike / Outlier": "Pico o valor atípico",
    "High-Frequency Noise": "Ruido de alta frecuencia",
    "Brake + Throttle Simultaneous": "Freno y acelerador simultáneos",
    "G-G Lateral Asymmetry": "Asimetría lateral G-G",
    "G-G Longitudinal Asymmetry": "Asimetría longitudinal G-G",
}

SEVERITY_ES = {
    "Critical": "Crítico",
    "Warning": "Advertencia",
    "Info": "Información",
}
SEVERITY_ORDER = {"Crítico": 0, "Advertencia": 1, "Información": 2}

CAUSE_ES = {
    "Missing data or sensor failure": "Pérdida de datos o falla del sensor",
    "Sensor stuck, loss of signal, or saturated": "Sensor bloqueado, pérdida de señal o saturado",
    "Sensor range exceeded or signal clipping": "Rango del sensor excedido o recorte de señal",
    "Electrical noise, loose connection, or transient": "Ruido eléctrico, conexión suelta o transitorio",
    "Electrical noise or mechanical vibration": "Ruido eléctrico o vibración mecánica",
    "Driver error, pedal misalignment, or sensor offset": "Error del piloto, desalineación de pedales o offset del sensor",
    "Vehicle setup, tire differences, or sensor offset": "Configuración del vehículo, diferencias en neumáticos o offset del sensor",
    "Brake bias, engine power distribution, or sensor offset": "Balance de frenos, distribución de potencia del motor o offset del sensor",
}

ACTION_ES = {
    "Interpolate or discard segment": "Interpolar o descartar el segmento",
    "Check sensor wiring, inspect for physical damage": "Revisar cableado del sensor, inspeccionar daños físicos",
    "Verify sensor range and signal conditioning": "Verificar rango del sensor y acondicionamiento de señal",
    "Inspect wiring, apply spike removal filter": "Inspeccionar cableado, aplicar filtro de eliminación de picos",
    "Apply low-pass filter or inspect mounting": "Aplicar filtro pasa-bajas o inspeccionar montaje",
    "Check pedal sensors and driver inputs": "Revisar sensores de pedal y entradas del piloto",
    "Check alignment, tire pressures, and sensor calibration": "Revisar alineación, presión de neumáticos y calibración del sensor",
    "Check brake balance and engine map": "Revisar balance de frenos y mapa del motor",
}

CHANNEL_TRANSLATIONS = {
    "accel_x": "Aceleración longitudinal",
    "accel_y": "Aceleración lateral",
    "brake_pressure": "Presión de freno",
    "throttle": "Acelerador",
    "speed_kmph": "Velocidad",
    "steering_angle": "Ángulo de dirección",
}

GG_LABELS_ES = {
    "Pure Acceleration": "Aceleración pura",
    "Pure Braking": "Frenado puro",
    "Pure Right Cornering": "Curva derecha",
    "Pure Left Cornering": "Curva izquierda",
    "Combined Accel out of Right": "Acel. + derecha",
    "Combined Accel out of Left": "Acel. + izquierda",
    "Trail Braking into Right": "Frenado + derecha",
    "Trail Braking into Left": "Frenado + izquierda",
    "Near Origin": "Baja carga dinámica",
}

def detect_nan_events(df, time_col, columns):
    events = []
    for col in columns:
        if col not in df.columns:
            continue
        nan_mask = df[col].isna()
        diff = np.diff(np.concatenate(([0], nan_mask.astype(int), [0])))
        starts = np.where(diff == 1)[0]
        ends = np.where(diff == -1)[0]
        for s, e in zip(starts, ends):
            if s < e:
                events.append(Event(
                    category="Integridad de datos",
                    type="Pérdida de datos",
                    severity="Advertencia",
                    channels=[col],
                    start_sample=int(s),
                    end_sample=int(e-1),
                    start_time=df[time_col].iloc[s],
                    end_time=df[time_col].iloc[e-1],
                    duration=df[time_col].iloc[e-1] - df[time_col].iloc[s],
                    description=f"Valores NaN en {col} desde {s} hasta {e-1}",
                    probable_cause="Pérdida de datos o falla del sensor",
                    recommended_action="Interpolar o descartar el segmento",
                ))
    return events

def detect_flatline(df, time_col, columns, window, tolerance):
    events = []
    for col in columns:
        if col not in df.columns:
            continue
        s = df[col].values
        if np.all(np.isnan(s)):
            continue
        s_series = pd.Series(s)
        s_interp = s_series.interpolate(limit_area='inside').bfill().ffill().values
        if len(s_interp) < window:
            continue
        var = pd.Series(s_interp).rolling(window, center=True).var().values
        low_var = var < tolerance
        diff = np.diff(np.concatenate(([0], low_var.astype(int), [0])))
        starts = np.where(diff == 1)[0]
        ends = np.where(diff == -1)[0]
        for s_i, e_i in zip(starts, ends):
            if e_i - s_i >= 5:
                segment = s_interp[s_i:e_i]
                if np.max(segment) - np.min(segment) < tolerance:
                    events.append(Event(
                        category="Integridad del sensor",
                        type="Sensor bloqueado / señal constante",
                        severity="Advertencia",
                        channels=[col],
                        start_sample=int(s_i),
                        end_sample=int(e_i-1),
                        start_time=df[time_col].iloc[s_i],
                        end_time=df[time_col].iloc[e_i-1],
                        duration=df[time_col].iloc[e_i-1] - df[time_col].iloc[s_i],
                        description=f"Señal plana en {col} de {s_i} a {e_i-1} (var < {tolerance})",
                        probable_cause="Sensor bloqueado, pérdida de señal o saturado",
                        recommended_action="Revisar cableado del sensor, inspeccionar daños físicos",
                    ))
    return events

def detect_saturation(df, time_col, columns, limits, epsilon):
    events = []
    for col in columns:
        if col not in df.columns:
            continue
        if col in limits:
            low, high = limits[col]
        else:
            s = df[col].dropna()
            if len(s) == 0:
                continue
            low = np.percentile(s, 1)
            high = np.percentile(s, 99)
        s = df[col].values
        low_thresh = low + epsilon * abs(low) if low != 0 else epsilon
        high_thresh = high - epsilon * abs(high) if high != 0 else -epsilon
        sat_mask = (s >= high_thresh) | (s <= low_thresh)
        diff = np.diff(np.concatenate(([0], sat_mask.astype(int), [0])))
        starts = np.where(diff == 1)[0]
        ends = np.where(diff == -1)[0]
        for s_i, e_i in zip(starts, ends):
            if e_i - s_i >= 3:
                segment = s[s_i:e_i]
                if np.mean(segment) > (high + low)/2:
                    limit_val = high
                    type_str = "Saturación superior"
                else:
                    limit_val = low
                    type_str = "Saturación inferior"
                events.append(Event(
                    category="Integridad del sensor",
                    type=type_str,
                    severity="Advertencia",
                    channels=[col],
                    start_sample=int(s_i),
                    end_sample=int(e_i-1),
                    start_time=df[time_col].iloc[s_i],
                    end_time=df[time_col].iloc[e_i-1],
                    duration=df[time_col].iloc[e_i-1] - df[time_col].iloc[s_i],
                    description=f"Saturación en {col} en límite {limit_val:.2f}",
                    metrics={"limit": limit_val},
                    probable_cause="Rango del sensor excedido o recorte de señal",
                    recommended_action="Verificar rango del sensor y acondicionamiento de señal",
                ))
    return events

def detect_spikes_mad(df, time_col, columns, threshold):
    events = []
    for col in columns:
        if col not in df.columns:
            continue
        s = df[col].values
        if np.all(np.isnan(s)):
            continue
        clean = s[~np.isnan(s)]
        if len(clean) < 10:
            continue
        median = np.median(clean)
        mad = median_abs_deviation(clean, scale='normal')
        if mad == 0:
            continue
        z_scores = np.abs((s - median) / mad)
        outliers = z_scores > threshold
        diff = np.diff(np.concatenate(([0], outliers.astype(int), [0])))
        starts = np.where(diff == 1)[0]
        ends = np.where(diff == -1)[0]
        for s_i, e_i in zip(starts, ends):
            if e_i - s_i >= 1:
                segment = s[s_i:e_i]
                max_val = np.max(np.abs(segment))
                events.append(Event(
                    category="Calidad de señal",
                    type="Pico o valor atípico",
                    severity="Advertencia",
                    channels=[col],
                    start_sample=int(s_i),
                    end_sample=int(e_i-1),
                    start_time=df[time_col].iloc[s_i],
                    end_time=df[time_col].iloc[e_i-1],
                    duration=df[time_col].iloc[e_i-1] - df[time_col].iloc[s_i],
                    description=f"Pico en {col} con desviación máxima {max_val:.2f}",
                    metrics={"max_deviation": max_val, "zscore_max": np.max(z_scores[s_i:e_i])},
                    probable_cause="Ruido eléctrico, conexión suelta o transitorio",
                    recommended_action="Inspeccionar cableado, aplicar filtro de eliminación de picos",
                ))
    return events

def detect_high_freq_noise(df, time_col, columns, fs, high_freq_threshold, ratio_warning):
    events = []
    for col in columns:
        if col not in df.columns:
            continue
        s = df[col].values
        s_clean = s[~np.isnan(s)]
        if len(s_clean) < 256:
            continue
        total, high, ratio = compute_high_freq_energy(s_clean, fs, high_freq_threshold)
        if np.isnan(ratio):
            continue
        if ratio > ratio_warning:
            events.append(Event(
                category="Calidad de señal",
                type="Ruido de alta frecuencia",
                severity="Información",
                channels=[col],
                start_sample=0,
                end_sample=len(s)-1,
                start_time=df[time_col].iloc[0],
                end_time=df[time_col].iloc[-1],
                duration=df[time_col].iloc[-1] - df[time_col].iloc[0],
                description=f"Ruido de alta frecuencia en {col}: relación HF = {ratio:.2f}",
                metrics={"hf_ratio": ratio, "hf_energy": high, "total_energy": total},
                probable_cause="Ruido eléctrico o vibración mecánica",
                recommended_action="Aplicar filtro pasa-bajas o inspeccionar montaje",
            ))
    return events

def detect_plausibility_brake_throttle(df, time_col, brake_col, throttle_col,
                                       brake_thresh, throttle_thresh, persistence_samples):
    events = []
    if brake_col not in df.columns or throttle_col not in df.columns:
        return events
    brake = df[brake_col].values
    throttle = df[throttle_col].values
    brake = pd.Series(brake).interpolate().bfill().ffill().values
    throttle = pd.Series(throttle).interpolate().bfill().ffill().values
    condition = (brake >= brake_thresh) & (throttle >= throttle_thresh)
    count = 0
    start_idx = None
    for i, val in enumerate(condition):
        if val:
            if count == 0:
                start_idx = i
            count += 1
        else:
            if count > persistence_samples and start_idx is not None:
                end_idx = i - 1
                events.append(Event(
                    category="Plausibilidad",
                    type="Freno y acelerador simultáneos",
                    severity="Crítico",
                    channels=[brake_col, throttle_col],
                    start_sample=int(start_idx),
                    end_sample=int(end_idx),
                    start_time=df[time_col].iloc[start_idx],
                    end_time=df[time_col].iloc[end_idx],
                    duration=df[time_col].iloc[end_idx] - df[time_col].iloc[start_idx],
                    description=f"Freno y acelerador aplicados simultáneamente durante {count} muestras",
                    probable_cause="Error del piloto, desalineación de pedales o offset del sensor",
                    recommended_action="Revisar sensores de pedal y entradas del piloto",
                ))
            count = 0
            start_idx = None
    if count > persistence_samples and start_idx is not None:
        end_idx = len(condition) - 1
        events.append(Event(
            category="Plausibilidad",
            type="Freno y acelerador simultáneos",
            severity="Crítico",
            channels=[brake_col, throttle_col],
            start_sample=int(start_idx),
            end_sample=int(end_idx),
            start_time=df[time_col].iloc[start_idx],
            end_time=df[time_col].iloc[end_idx],
            duration=df[time_col].iloc[end_idx] - df[time_col].iloc[start_idx],
            description=f"Freno y acelerador aplicados simultáneamente durante {count} muestras (hasta el final)",
            probable_cause="Error del piloto, desalineación de pedales o offset del sensor",
            recommended_action="Revisar sensores de pedal y entradas del piloto",
        ))
    return events

def detect_gg_asymmetry(ax, ay, units, g_conversion, time_col, percentile=95):
    events = []
    if units.lower() == "m/s2":
        ax = ax / g_conversion
        ay = ay / g_conversion
    left = ay[ay > 0]
    right = ay[ay < 0]
    accel = ax[ax > 0]
    brake = ax[ax < 0]
    if len(left) > 0 and len(right) > 0:
        p_left, p_right, asym_lat = compute_asymmetry(left, right, percentile)
        if abs(asym_lat) > 0.15:
            events.append(Event(
                category="Dinámica vehicular",
                type="Asimetría lateral G-G",
                severity="Información",
                channels=["accel_y"],
                start_sample=0,
                end_sample=len(ax)-1,
                start_time=time_col.iloc[0],
                end_time=time_col.iloc[-1],
                duration=time_col.iloc[-1] - time_col.iloc[0],
                description=f"Asimetría lateral: {asym_lat:.2f} (izq {p_left:.2f}G, der {p_right:.2f}G)",
                metrics={"asymmetry": asym_lat, "left": p_left, "right": p_right},
                probable_cause="Configuración del vehículo, diferencias en neumáticos o offset del sensor",
                recommended_action="Revisar alineación, presión de neumáticos y calibración del sensor",
            ))
    if len(accel) > 0 and len(brake) > 0:
        p_accel, p_brake, asym_long = compute_asymmetry(accel, brake, percentile)
        if abs(asym_long) > 0.15:
            events.append(Event(
                category="Dinámica vehicular",
                type="Asimetría longitudinal G-G",
                severity="Información",
                channels=["accel_x"],
                start_sample=0,
                end_sample=len(ax)-1,
                start_time=time_col.iloc[0],
                end_time=time_col.iloc[-1],
                duration=time_col.iloc[-1] - time_col.iloc[0],
                description=f"Asimetría longitudinal: {asym_long:.2f} (acel {p_accel:.2f}G, freno {p_brake:.2f}G)",
                metrics={"asymmetry": asym_long, "accel": p_accel, "brake": p_brake},
                probable_cause="Balance de frenos, distribución de potencia del motor o offset del sensor",
                recommended_action="Revisar balance de frenos y mapa del motor",
            ))
    return events

def run_all_detectors(df, time_col, config):
    events = []
    cfg = config
    fs = cfg["sampling_frequency"]
    all_cols = [
        col for col in df.select_dtypes(include=[np.number]).columns.tolist()
        if col != "time" and not col.endswith("_filtered")
    ]
    events.extend(detect_nan_events(df, time_col, all_cols))
    events.extend(detect_flatline(df, time_col, all_cols, cfg["flatline_window"], cfg["flatline_tolerance"]))
    events.extend(detect_saturation(df, time_col, all_cols, cfg["saturation_limits"], cfg["saturation_epsilon"]))
    events.extend(detect_spikes_mad(df, time_col, all_cols, cfg["outlier_mad_threshold"]))
    events.extend(detect_high_freq_noise(df, time_col, all_cols, fs, cfg["high_freq_threshold"], cfg["hf_ratio_warning"]))
    brake_col = "brake_pressure" if "brake_pressure" in df.columns else None
    throttle_col = "throttle" if "throttle" in df.columns else None
    if brake_col and throttle_col:
        events.extend(detect_plausibility_brake_throttle(
            df, time_col, brake_col, throttle_col,
            cfg["brake_threshold"], cfg["throttle_threshold"],
            cfg["persistence_samples"]
        ))
    if "accel_x" in df.columns and "accel_y" in df.columns:
        ax = df["accel_x"].values
        ay = df["accel_y"].values
        ax = pd.Series(ax).interpolate().bfill().ffill().values
        ay = pd.Series(ay).interpolate().bfill().ffill().values
        events.extend(detect_gg_asymmetry(
            ax, ay, cfg["axis_units"], cfg["g_conversion"],
            df[time_col], cfg["gg_percentile"]
        ))
    return events

def run_full_analysis(df, config):
    df_out = df.copy()
    cfg = config
    numeric_cols = df_out.select_dtypes(include=[np.number]).columns.tolist()
    if "time" in numeric_cols:
        numeric_cols.remove("time")
    fs = cfg["sampling_frequency"]
    cutoff = cfg["cutoff_freq"]
    order = cfg["filter_order"]
    filter_type = cfg["filter_type"]
    try:
        sos = design_filter(filter_type, order, cutoff, fs)
    except Exception as e:
        print(f"Filter design failed: {e}")
        sos = None
    if sos is not None:
        for col in numeric_cols:
            s = df_out[col].values
            s_series = pd.Series(s)
            s_interp = s_series.interpolate(limit_area='inside').bfill().ffill().values
            filtered = apply_filter(s_interp, sos)
            df_out[f"{col}_filtered"] = filtered
    events = run_all_detectors(df_out, "time", cfg)
    return df_out, events

# Funciones auxiliares G-G (conservadas del diseño anterior)
def classify_gg_regions(lat_g, long_g, threshold=0.15):
    labels = np.full_like(lat_g, "Near Origin", dtype=object)
    colors = {
        "Pure Acceleration": "purple",
        "Pure Braking": "saddlebrown",
        "Pure Right Cornering": "orange",
        "Pure Left Cornering": "dodgerblue",
        "Combined Accel out of Right": "red",
        "Combined Accel out of Left": "limegreen",
        "Trail Braking into Right": "darkblue",
        "Trail Braking into Left": "gold",
        "Near Origin": "gray",
    }
    lat = np.asarray(lat_g, dtype=float)
    lon = np.asarray(long_g, dtype=float)
    T = threshold
    labels[(np.abs(lat) < T) & (lon > T)] = "Pure Acceleration"
    labels[(np.abs(lat) < T) & (lon < -T)] = "Pure Braking"
    labels[(lat < -T) & (np.abs(lon) < T)] = "Pure Right Cornering"
    labels[(lat > T) & (np.abs(lon) < T)] = "Pure Left Cornering"
    labels[(lat < -T) & (lon > T)] = "Combined Accel out of Right"
    labels[(lat > T) & (lon > T)] = "Combined Accel out of Left"
    labels[(lat < -T) & (lon < -T)] = "Trail Braking into Right"
    labels[(lat > T) & (lon < -T)] = "Trail Braking into Left"
    return labels, colors

def compute_gg_envelope(lat_g, long_g, n_bins=72, percentile=95, smooth_factor=0.5):
    lat = np.asarray(lat_g, dtype=float)
    lon = np.asarray(long_g, dtype=float)
    valid = np.isfinite(lat) & np.isfinite(lon)
    lat, lon = lat[valid], lon[valid]
    if len(lat) < n_bins:
        return None
    theta = np.arctan2(lon, lat)
    radius = np.sqrt(lat**2 + lon**2)
    bins = np.linspace(-np.pi, np.pi, n_bins + 1)
    bin_centers = (bins[:-1] + bins[1:]) / 2
    max_radii = []
    angles_used = []
    for i in range(n_bins):
        in_bin = (theta >= bins[i]) & (theta < bins[i+1])
        r_bin = radius[in_bin]
        if len(r_bin) > 0:
            r_p = np.percentile(r_bin, percentile)
            if np.isfinite(r_p) and r_p > 0:
                max_radii.append(r_p)
                angles_used.append(bin_centers[i])
    if len(max_radii) < 3:
        return None
    max_radii = np.array(max_radii)
    angles_used = np.array(angles_used)
    order = np.argsort(angles_used)
    angles_used = angles_used[order]
    max_radii = max_radii[order]
    x_env = max_radii * np.cos(angles_used)
    y_env = max_radii * np.sin(angles_used)
    x_env = np.append(x_env, x_env[0])
    y_env = np.append(y_env, y_env[0])
    if smooth_factor is not None:
        try:
            tck, u = splprep([x_env, y_env], s=smooth_factor, per=1)
            u_new = np.linspace(0, 1, 200)
            x_smooth, y_smooth = splev(u_new, tck)
            return np.column_stack([x_smooth, y_smooth])
        except Exception:
            pass
    return np.column_stack([x_env, y_env])

def compute_gg_metrics(lat_g, long_g, time_array, percentile=95):
    lat = np.asarray(lat_g, dtype=float)
    lon = np.asarray(long_g, dtype=float)
    valid = np.isfinite(lat) & np.isfinite(lon)
    lat, lon = lat[valid], lon[valid]
    if time_array is not None:
        time_arr = np.asarray(time_array, dtype=float)[valid]
    else:
        time_arr = np.arange(len(lat))
    def robust_g(data, p):
        if len(data) == 0:
            return 0.0
        return np.percentile(np.abs(data), p)
    G_left = robust_g(lat[lat > 0], percentile)
    G_right = robust_g(lat[lat < 0], percentile)
    G_accel = robust_g(lon[lon > 0], percentile)
    G_braking = robust_g(lon[lon < 0], percentile)
    lat_asym = 0.0
    if max(G_left, G_right) > 0:
        lat_asym = (G_left - G_right) / max(G_left, G_right)
    long_asym = 0.0
    if max(G_accel, G_braking) > 0:
        long_asym = (G_accel - G_braking) / max(G_accel, G_braking)
    g_combined = np.sqrt(lat**2 + lon**2)
    max_combined = np.nanmax(g_combined)
    idx_max = np.nanargmax(g_combined)
    timestamp_max = float(time_arr[idx_max]) if len(time_arr) > 0 else 0.0
    return {
        'G_left': G_left, 'G_right': G_right,
        'G_accel': G_accel, 'G_braking': G_braking,
        'lat_asym': lat_asym, 'long_asym': long_asym,
        'max_combined': max_combined, 'timestamp_max_combined': timestamp_max,
    }

def generate_gg_diagnosis(metrics, centroid_shift=None):
    diag = []
    asym_lat = metrics['lat_asym']
    asym_long = metrics['long_asym']
    diag.append("--- ASIMETRÍA LATERAL ---")
    if abs(asym_lat) < 0.05:
        diag.append("Envolvente lateral aproximadamente simétrica.")
    elif abs(asym_lat) < 0.15:
        diag.append("Asimetría lateral moderada entre curvas a izquierda y derecha.")
    else:
        diag.append("Asimetría direccional significativa en la envolvente G-G.")
    diag.append(f"Curva izquierda: {metrics['G_left']:.2f} G  |  Curva derecha: {metrics['G_right']:.2f} G  |  Asimetría: {asym_lat*100:.1f} %")
    diag.append("")
    diag.append("--- ASIMETRÍA LONGITUDINAL ---")
    if abs(asym_long) < 0.05:
        diag.append("Capacidad de aceleración/frenado simétrica.")
    elif abs(asym_long) < 0.15:
        diag.append("Asimetría longitudinal moderada entre aceleración y frenado.")
    else:
        diag.append("Asimetría longitudinal significativa.")
    diag.append(f"Aceleración: {metrics['G_accel']:.2f} G  |  Frenado: {metrics['G_braking']:.2f} G  |  Asimetría: {asym_long*100:.1f} %")
    diag.append("")
    diag.append("--- DIAGNÓSTICO TÉCNICO ---")
    if abs(asym_lat) >= 0.15 or abs(asym_long) >= 0.15:
        diag.append("Posibles causas (requieren validación):")
        causes = [
            "Configuración del vehículo: diferencia de presión/condición entre neumáticos, alineación (camber/toe), distribución de carga lateral, configuración asimétrica de suspensión, diferencias de grip, recorrido del circuito predominantemente hacia una dirección.",
            "Instrumentación: offset del acelerómetro, mala calibración del IMU, montaje inclinado del sensor, desalineación de ejes del IMU respecto al vehículo, saturación del sensor, drift o bias.",
            "Características del circuito: trazado con predominancia de curvas en una dirección."
        ]
        for c in causes:
            diag.append("- " + c)
    else:
        diag.append("No se detectan asimetrías significativas. El vehículo presenta un comportamiento equilibrado dentro de la muestra analizada.")
    if centroid_shift is not None and centroid_shift > 0.10:
        diag.append("\n⚠️ ADVERTENCIA: Posible offset o bias del sensor inercial.")
        diag.append("La distribución G-G presenta un desplazamiento sistemático respecto al origen.")
        diag.append("Se recomienda verificar la calibración y orientación del IMU.")
    return "\n".join(diag)

def generate_report(raw_df, processed_df, metadata, events_registry, config):
    lines = []
    lines.append("=" * 70)
    lines.append("INFORME DE ANÁLISIS DE TELEMETRÍA — FÓRMULA SAE")
    lines.append("=" * 70)
    lines.append("")
    # 1. INFORMACIÓN DEL ARCHIVO
    lines.append("1. INFORMACIÓN DEL ARCHIVO")
    lines.append("-" * 40)
    lines.append(f"  Archivo: {metadata.get('file_name', 'N/A')}")
    lines.append(f"  Número de muestras: {metadata['num_samples']}")
    lines.append(f"  Duración: {metadata['duration_seconds']:.2f} s")
    lines.append(f"  Frecuencia de muestreo: {metadata['sampling_frequency']} Hz")
    lines.append(f"  Canales disponibles: {len(metadata['available_channels'])}")
    lines.append("")
    # 2. RESUMEN DEL ANÁLISIS
    lines.append("2. RESUMEN DEL ANÁLISIS")
    lines.append("-" * 40)
    lines.append(f"  Muestras procesadas: {metadata['num_samples']}")
    lines.append(f"  Duración del registro: {metadata['duration_seconds']:.2f} s")
    lines.append(f"  Frecuencia: {config['sampling_frequency']} Hz")
    lines.append("")
    # 3. CONFIGURACIÓN DEL ANÁLISIS
    lines.append("3. CONFIGURACIÓN DEL ANÁLISIS")
    lines.append("-" * 40)
    lines.append(f"  Tipo de filtro: {config['filter_type']}")
    lines.append(f"  Orden: {config['filter_order']}")
    lines.append(f"  Frecuencia de corte: {config['cutoff_freq']} Hz")
    lines.append(f"  Umbral freno: {config['brake_threshold']}")
    lines.append(f"  Umbral acelerador: {config['throttle_threshold']}")
    lines.append(f"  Persistencia mínima (freno+acelerador): {config['persistence_samples']} muestras (≈{config['persistence_samples']/config['sampling_frequency']*1000:.0f} ms)")
    lines.append(f"  Percentil G-G: {config['gg_percentile']}%")
    lines.append("")
    # 4. ACONDICIONAMIENTO DE SEÑAL
    lines.append("4. ACONDICIONAMIENTO DE SEÑAL")
    lines.append("-" * 40)
    lines.append(f"  Se aplicó un filtro pasa-bajas {config['filter_type']} de orden {config['filter_order']} con frecuencia de corte {config['cutoff_freq']} Hz.")
    lines.append("  El filtro fue implementado mediante 'sosfiltfilt', que proporciona un filtrado de fase cero,")
    lines.append("  preservando la alineación temporal de los eventos dinámicos.")
    lines.append("  Este procedimiento reduce ruido de alta frecuencia y vibraciones estructurales sin introducir retardo.")
    lines.append("")
    # 5. ANÁLISIS DE CARGAS G
    lines.append("5. ANÁLISIS DE CARGAS G")
    lines.append("-" * 40)
    ax_col = "accel_x_filtered" if "accel_x_filtered" in processed_df.columns else "accel_x"
    ay_col = "accel_y_filtered" if "accel_y_filtered" in processed_df.columns else "accel_y"
    if ax_col in processed_df.columns and ay_col in processed_df.columns:
        ax = processed_df[ax_col].values
        ay = processed_df[ay_col].values
        time_arr = processed_df["time"].values
        ax = pd.Series(ax).interpolate().bfill().ffill().values
        ay = pd.Series(ay).interpolate().bfill().ffill().values
        if config['axis_units'].lower() == "m/s2":
            g_conv = config['g_conversion']
            ax_g = ax / g_conv
            ay_g = ay / g_conv
        else:
            ax_g, ay_g = ax, ay
        g_comb = np.sqrt(ax_g**2 + ay_g**2)
        max_g = np.nanmax(g_comb)
        idx_max = np.nanargmax(g_comb)
        t_max = time_arr[idx_max] if len(time_arr) > 0 else 0.0
        lines.append(f"  Máxima G combinada: {max_g:.3f} G (sobre señal filtrada)")
        lines.append(f"  Instante de G máxima: t = {t_max:.3f} s")
        lines.append("")
        # 6. DIAGNÓSTICO DEL DIAGRAMA G-G
        lines.append("6. DIAGNÓSTICO DEL DIAGRAMA G-G")
        lines.append("-" * 40)
        lat = ay_g
        lon = ax_g
        valid = np.isfinite(lat) & np.isfinite(lon)
        lat, lon = lat[valid], lon[valid]
        metrics = compute_gg_metrics(lat, lon, time_arr[valid], config['gg_percentile'])
        lines.append(f"  G lateral izquierda (percentil {config['gg_percentile']}): {metrics['G_left']:.3f} G")
        lines.append(f"  G lateral derecha: {metrics['G_right']:.3f} G")
        lines.append(f"  Asimetría lateral: {metrics['lat_asym']*100:.1f} %")
        lines.append(f"  G aceleración: {metrics['G_accel']:.3f} G")
        lines.append(f"  G frenado: {metrics['G_braking']:.3f} G")
        lines.append(f"  G combinada máxima: {metrics['max_combined']:.3f} G")
        lines.append(f"  Timestamp de G máxima: {metrics['timestamp_max_combined']:.3f} s")
        lines.append("")
        asym_lat = metrics['lat_asym']
        if abs(asym_lat) < 0.05:
            lines.append("  INTERPRETACIÓN: La envolvente lateral es simétrica. La diferencia entre curvas izquierda y derecha no es significativa.")
        elif abs(asym_lat) < 0.15:
            lines.append("  INTERPRETACIÓN: Se observa una asimetría lateral moderada. La diferencia puede estar relacionada con el trazado del circuito o con la configuración del vehículo.")
        else:
            lines.append("  INTERPRETACIÓN: Asimetría direccional significativa. Se recomienda revisar la puesta a punto del vehículo y la calibración del sensor inercial.")
        lines.append("")
        if abs(asym_lat) >= 0.05:
            lines.append("  Posibles causas (requieren validación):")
            lines.append("    - Configuración del vehículo: diferencias en presión de neumáticos, alineación, distribución de carga o ajuste asimétrico de suspensión.")
            lines.append("    - Instrumentación: offset del IMU, desalineación del sensor, saturación o drift.")
            lines.append("    - Trazado: predominio de curvas hacia una dirección.")
        lines.append("")
    else:
        lines.append("  No se dispone de los canales de aceleración.")
        lines.append("")
    # 7. INTEGRIDAD DE LOS SENSORES
    lines.append("7. INTEGRIDAD DE LOS SENSORES")
    lines.append("-" * 40)
    sensor_events = events_registry.filter(category="Integridad del sensor")
    if not sensor_events:
        lines.append("  No se detectaron eventos de integridad en los sensores.")
    else:
        lines.append(f"  Eventos detectados: {len(sensor_events)}")
        for evt in sensor_events[:10]:
            ch_disp = ', '.join([CHANNEL_TRANSLATIONS.get(c, c) for c in evt.channels])
            lines.append(f"    {evt.id}: {TYPE_ES.get(evt.type, evt.type)} en {ch_disp} desde {evt.start_time:.2f}s hasta {evt.end_time:.2f}s")
    lines.append("")
    # 8. CALIDAD DE LAS SEÑALES
    lines.append("8. CALIDAD DE LAS SEÑALES")
    lines.append("-" * 40)
    quality_events = events_registry.filter(category="Calidad de señal")
    if not quality_events:
        lines.append("  No se detectaron eventos de calidad de señal.")
    else:
        lines.append(f"  Eventos detectados: {len(quality_events)}")
        for evt in quality_events[:10]:
            ch_disp = ', '.join([CHANNEL_TRANSLATIONS.get(c, c) for c in evt.channels])
            lines.append(f"    {evt.id}: {TYPE_ES.get(evt.type, evt.type)} en {ch_disp} desde {evt.start_time:.2f}s hasta {evt.end_time:.2f}s")
    lines.append("")
    # 9. EVENTOS DE SEGURIDAD Y PLAUSIBILIDAD
    lines.append("9. EVENTOS DE SEGURIDAD Y PLAUSIBILIDAD")
    lines.append("-" * 40)
    plaus_events = events_registry.filter(category="Plausibilidad")
    if not plaus_events:
        lines.append("  No se detectaron eventos de plausibilidad (freno + acelerador simultáneos).")
    else:
        lines.append(f"  Eventos detectados: {len(plaus_events)}")
        lines.append(f"  Criterio: aplicación simultánea > {config['persistence_samples']} muestras consecutivas (~{config['persistence_samples']/config['sampling_frequency']*1000:.0f} ms)")
        for evt in plaus_events[:10]:
            lines.append(f"    {evt.id}: desde {evt.start_time:.2f}s hasta {evt.end_time:.2f}s, duración {evt.duration:.3f} s")
            lines.append(f"      Causa probable: {CAUSE_ES.get(evt.probable_cause, evt.probable_cause)}")
            lines.append(f"      Acción recomendada: {ACTION_ES.get(evt.recommended_action, evt.recommended_action)}")
    lines.append("")
    # 10. RESUMEN DE ANOMALÍAS
    lines.append("10. RESUMEN DE ANOMALÍAS")
    lines.append("-" * 40)
    total = len(events_registry)
    if total == 0:
        lines.append("  No se detectaron anomalías.")
    else:
        summary = events_registry.get_summary()
        cat_es = {}
        for k, v in summary['by_category'].items():
            cat_es[CATEGORY_ES.get(k, k)] = v
        sev_es = {}
        for k, v in summary['by_severity'].items():
            sev_es[SEVERITY_ES.get(k, k)] = v
        lines.append(f"  Total de eventos: {total}")
        lines.append(f"  Críticos: {summary['critical_count']}")
        lines.append("  Por categoría:")
        for cat, cnt in cat_es.items():
            lines.append(f"    {cat}: {cnt}")
        lines.append("  Por severidad:")
        for sev, cnt in sev_es.items():
            lines.append(f"    {sev}: {cnt}")
    lines.append("")
    # 11. DIAGNÓSTICO GENERAL
    lines.append("11. DIAGNÓSTICO GENERAL")
    lines.append("-" * 40)
    estado = "ADECUADO"
    if summary.get('critical_count', 0) > 0 or (metrics and abs(metrics.get('lat_asym', 0)) >= 0.15):
        estado = "REQUIERE REVISIÓN"
    elif metrics and abs(metrics.get('lat_asym', 0)) >= 0.05:
        estado = "ADECUADO, con observaciones"
    lines.append(f"  Estado general del registro: {estado}")
    lines.append("")
    # 12. ACCIONES RECOMENDADAS
    lines.append("12. ACCIONES RECOMENDADAS")
    lines.append("-" * 40)
    criticals = summary.get('critical_count', 0)
    warnings = sev_es.get('Advertencia', 0)
    if criticals > 0:
        lines.append("  Prioridad alta:")
        lines.append("    1. Revisar los eventos de plausibilidad (freno + acelerador simultáneos).")
        lines.append("    2. Verificar calibración de pedales y sensor inercial.")
    if warnings > 0:
        lines.append("  Prioridad media:")
        lines.append("    3. Inspeccionar conexiones y cableado de sensores con eventos de integridad.")
        lines.append("    4. Evaluar si el ruido de alta frecuencia afecta a canales críticos.")
    lines.append("  Prioridad baja:")
    lines.append("    5. Continuar monitoreando la asimetría lateral en próximas adquisiciones.")
    lines.append("")
    # 13. CONCLUSIONES
    lines.append("13. CONCLUSIONES")
    lines.append("-" * 40)
    if metrics:
        max_g_val = metrics['max_combined']
        lines.append(f"  El análisis de telemetría se realizó correctamente. Los datos fueron acondicionados con un filtro de fase cero para preservar la dinámica del vehículo.")
        lines.append(f"  La máxima aceleración combinada registrada fue de {max_g_val:.3f} G.")
        if abs(metrics.get('lat_asym', 0)) < 0.05:
            lines.append("  El diagrama G-G muestra un comportamiento lateral simétrico, indicando un adecuado balance en curvas.")
        else:
            lines.append(f"  Se identificó una asimetría lateral del {abs(metrics.get('lat_asym',0))*100:.1f}%, la cual podría estar relacionada con la configuración del vehículo o el trazado del circuito.")
        lines.append(f"  Se detectaron {total} anomalías en total, con {criticals} eventos críticos.")
        if criticals == 0:
            lines.append("  No se encontraron eventos de plausibilidad que comprometan la seguridad.")
        else:
            lines.append("  Los eventos críticos requieren atención para garantizar la integridad de los sensores.")
        lines.append("  En general, la calidad de los datos permite un análisis fiable de la dinámica vehicular.")
    else:
        lines.append("  No se pudieron calcular métricas G-G por falta de canales de aceleración.")
    lines.append("")
    lines.append("=" * 70)
    lines.append("Fin del informe.")
    return "\n".join(lines)

# =============================================================================
# HILO DE ANÁLISIS
# =============================================================================
class AnalysisThread(QThread):
    result_ready = pyqtSignal(object, object)
    error = pyqtSignal(str)

    def __init__(self, df, config):
        super().__init__()
        self.df = df
        self.config = config

    def run(self):
        try:
            df_out, events = run_full_analysis(self.df, self.config)
            self.result_ready.emit(df_out, events)
        except Exception as e:
            self.error.emit(str(e) + "\n" + traceback.format_exc())

# =============================================================================
# LIENZO MATPLOTLIB
# =============================================================================
class MplCanvas(FigureCanvas):
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi, facecolor=C("bg0"))
        super(MplCanvas, self).__init__(self.fig)
        self.setParent(parent)
        self.axes = self.fig.add_subplot(111)
        self.axes.set_facecolor(C("bg1"))
        self.axes.tick_params(colors=C("text_w"))
        for spine in self.axes.spines.values():
            spine.set_color(C("text_w"))
        self.fig.subplots_adjust(left=0.08, right=0.95, top=0.95, bottom=0.08)

# =============================================================================
# VENTANA INDEPENDIENTE DEL DIAGRAMA G-G
# =============================================================================
class GGWindow(QMainWindow):
    """Ventana independiente para el diagrama G-G con mayor tamaño y controles."""
    def __init__(self, parent_main_window):
        super().__init__()
        self.main_window = parent_main_window
        self.setWindowTitle("Diagrama G-G — Ventana independiente")
        self.resize(1200, 800)
        self.setStyleSheet(parent_main_window.styleSheet())
        self.setup_ui()

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # Controles superiores (copiados de la pestaña)
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("Unidades:"))
        self.cmb_units = QComboBox()
        self.cmb_units.addItems(["G", "m/s2"])
        self.cmb_units.setCurrentText(self.main_window.config["axis_units"])
        self.cmb_units.currentTextChanged.connect(self.update_plot)
        ctrl.addWidget(self.cmb_units)

        ctrl.addWidget(QLabel("Envolvente:"))
        self.cmb_env = QComboBox()
        self.cmb_env.addItems(["Ninguna", "Convex Hull", "Percentil robusto"])
        self.cmb_env.setCurrentIndex(2)
        self.cmb_env.currentTextChanged.connect(self.update_plot)
        ctrl.addWidget(self.cmb_env)
        ctrl.addStretch()
        main_layout.addLayout(ctrl)

        # Splitter horizontal
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter, 1)

        # Lado izquierdo: gráfica grande
        self.canvas = MplCanvas(self, width=10, height=8, dpi=100)
        toolbar = NavigationToolbar(self.canvas, self)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0,0,0,0)
        left_layout.addWidget(toolbar)
        left_layout.addWidget(self.canvas)
        splitter.addWidget(left)

        # Lado derecho: tarjetas de métricas
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8,8,8,8)

        def make_card(title):
            frame = QFrame()
            frame.setStyleSheet(f"background-color: {C('bg2')}; border: 1px solid {C('border')}; border-radius: 6px;")
            layout = QVBoxLayout(frame)
            layout.setContentsMargins(10,6,10,6)
            lbl_title = QLabel(title)
            lbl_title.setStyleSheet(f"color: {C('text_g')}; font-size: 11px;")
            lbl_val = QLabel("--")
            lbl_val.setStyleSheet(f"color: {C('cyan')}; font-size: 16px; font-weight: bold;")
            layout.addWidget(lbl_title)
            layout.addWidget(lbl_val)
            return frame, lbl_val

        self.card_left, self.lbl_left_val = make_card("Curva izquierda")
        self.card_right, self.lbl_right_val = make_card("Curva derecha")
        self.card_accel, self.lbl_accel_val = make_card("Aceleración")
        self.card_braking, self.lbl_braking_val = make_card("Frenado")
        self.card_maxg, self.lbl_maxg_val = make_card("G combinada máxima")
        self.card_asym, self.lbl_asym_val = make_card("Asimetría lateral")

        right_layout.addWidget(self.card_left)
        right_layout.addWidget(self.card_right)
        right_layout.addWidget(self.card_accel)
        right_layout.addWidget(self.card_braking)
        right_layout.addWidget(self.card_maxg)
        right_layout.addWidget(self.card_asym)
        right_layout.addStretch()

        self.status_label = QLabel("Estado dinámico:\nEQUILIBRADO")
        self.status_label.setStyleSheet(f"color: {C('green')}; font-size: 14px; font-weight: bold; padding: 8px;")
        right_layout.addWidget(self.status_label)
        splitter.addWidget(right)
        splitter.setSizes([900, 300])

        # Diagnóstico inferior
        diag_group = QGroupBox("DIAGNÓSTICO DEL DIAGRAMA G-G")
        diag_layout = QVBoxLayout(diag_group)
        self.diag_text = QTextEdit()
        self.diag_text.setReadOnly(True)
        self.diag_text.setMaximumHeight(120)
        diag_layout.addWidget(self.diag_text)
        main_layout.addWidget(diag_group)

    def update_plot(self):
        """Llama a la misma lógica de plot_gg pero dibujando en este canvas."""
        # Reutilizamos la función de la ventana principal, pasando los objetos de esta ventana
        self.main_window._plot_gg_in_canvas(
            canvas=self.canvas,
            units=self.cmb_units.currentText(),
            envelope=self.cmb_env.currentText(),
            update_func=self._update_metrics_and_diag
        )

    def _update_metrics_and_diag(self, metrics, centroid_shift):
        self.lbl_left_val.setText(f"{metrics['G_left']:.2f} G")
        self.lbl_right_val.setText(f"{metrics['G_right']:.2f} G")
        self.lbl_accel_val.setText(f"{metrics['G_accel']:.2f} G")
        self.lbl_braking_val.setText(f"{metrics['G_braking']:.2f} G")
        self.lbl_maxg_val.setText(f"{metrics['max_combined']:.2f} G")
        self.lbl_asym_val.setText(f"{metrics['lat_asym']*100:.1f} %")

        asym = abs(metrics['lat_asym'])
        if asym < 0.05:
            estado = "EQUILIBRADO"
            color = C("green")
        elif asym < 0.15:
            estado = "REVISAR"
            color = C("gold")
        else:
            estado = "ASIMETRÍA SIGNIFICATIVA"
            color = C("red")
        self.status_label.setText(f"Estado dinámico:\n{estado}")
        self.status_label.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: bold;")

        diagnosis = generate_gg_diagnosis(metrics, centroid_shift)
        self.diag_text.setText(diagnosis)

# =============================================================================
# VENTANA PRINCIPAL
# =============================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Análisis de Telemetría — Formula SAE")
        self.resize(1400, 850)
        self.setStyleSheet(f"""
            QMainWindow {{ background-color: {C("bg0")}; }}
            QWidget {{ background-color: {C("bg0")}; color: {C("text_w")}; font-family: {FONT}; }}
            QLabel {{ color: {C("text_w")}; }}
            QPushButton {{
                background-color: {C("bg2")}; color: {C("text_w")};
                border: 1px solid {C("border")}; border-radius: 8px;
                padding: 8px 16px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {C("bg3")}; border-color: {C("cyan")}; }}
            QPushButton:pressed {{ background-color: {C("cyan")}; color: {C("bg0")}; }}
            QPushButton:disabled {{ color: {C("text_g")}; }}
            QTabWidget::pane {{ border: 1px solid {C("border")}; background: {C("bg1")}; border-radius: 12px; }}
            QTabBar::tab {{
                background: {C("bg2")}; color: {C("text_g")}; padding: 10px 24px;
                font-weight: bold; border-top-left-radius: 8px; border-top-right-radius: 8px;
                border: 1px solid {C("border")}; margin-right: 2px;
            }}
            QTabBar::tab:selected {{ background: {C("bg1")}; color: {C("cyan")}; border-bottom: 2px solid {C("cyan")}; }}
            QTabBar::tab:hover:!selected {{ background: {C("bg3")}; color: {C("gold")}; }}
            QTableWidget {{ background: {C("bg1")}; color: {C("text_w")}; gridline-color: {C("border")}; }}
            QHeaderView::section {{ background: {C("bg2")}; color: {C("text_w")}; }}
            QTextEdit {{ background: {C("bg1")}; color: {C("text_w")}; border: 1px solid {C("border")}; border-radius: 8px; }}
            QGroupBox {{ color: {C("text_w")}; border: 1px solid {C("border")}; border-radius: 8px; margin-top: 1ex; }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 8px; }}
            QComboBox, QSpinBox, QDoubleSpinBox {{
                background: {C("bg1")}; color: {C("text_w")}; border: 1px solid {C("border")};
                border-radius: 6px; padding: 4px 8px;
            }}
            QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{ border-color: {C("cyan")}; }}
            QCheckBox {{ color: {C("text_w")}; }}
        """)

        self.raw_data = None
        self.processed_data = None
        self.metadata = {}
        self.analysis_thread = None
        self.event_registry = EventRegistry()
        self.config = {
            "sampling_frequency": 100,
            "filter_type": "butter",
            "filter_order": 4,
            "cutoff_freq": 5.0,
            "brake_threshold": 0.5,
            "throttle_threshold": 0.5,
            "persistence_samples": 10,
            "flatline_window": 20,
            "flatline_tolerance": 0.001,
            "saturation_limits": {
                "accel_x": (-1.5, 1.5),
                "accel_y": (-1.5, 1.5),
                "brake_pressure": (0, 100),
                "throttle": (0, 100),
                "steering_angle": (-45, 45),
            },
            "saturation_epsilon": 0.02,
            "outlier_mad_threshold": 3.5,
            "high_freq_threshold": 15.0,
            "hf_ratio_warning": 0.3,
            "gg_percentile": 95,
            "axis_units": "G",
            "g_conversion": 9.80665,
        }
        self.gg_windows = []  # lista de ventanas G-G abiertas
        self.setup_ui()

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # Barra superior
        top_bar = QHBoxLayout()
        self.btn_load = QPushButton("📂 Cargar archivo")
        self.btn_load.clicked.connect(self.load_file)
        top_bar.addWidget(self.btn_load)

        self.btn_example = QPushButton("📁 Cargar ejemplo (data.xlsx)")
        self.btn_example.clicked.connect(self.load_example)
        top_bar.addWidget(self.btn_example)

        self.btn_analyze = QPushButton("🚀 Iniciar análisis")
        self.btn_analyze.clicked.connect(self.run_analysis)
        self.btn_analyze.setEnabled(False)
        top_bar.addWidget(self.btn_analyze)

        self.status_label = QLabel("Listo")
        self.status_label.setStyleSheet(f"color: {C('text_g')};")
        top_bar.addWidget(self.status_label)
        top_bar.addStretch()
        main_layout.addLayout(top_bar)

        # Pestañas
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        self.setup_config_tab()
        self.setup_signals_tab()
        self.setup_gg_tab()
        self.setup_events_tab()
        self.setup_report_tab()

    def setup_config_tab(self):
        tab = QWidget()
        self.tabs.addTab(tab, "⚙️ Configuración")
        layout = QVBoxLayout(tab)

        g1 = QGroupBox("Filtros")
        form = QFormLayout()
        self.cmb_filter = QComboBox()
        self.cmb_filter.addItems(["butter", "cheby1", "cheby2", "ellip"])
        form.addRow("Tipo:", self.cmb_filter)
        self.spin_order = QSpinBox()
        self.spin_order.setRange(1, 8)
        self.spin_order.setValue(self.config["filter_order"])
        form.addRow("Orden:", self.spin_order)
        self.dspin_cutoff = QDoubleSpinBox()
        self.dspin_cutoff.setRange(0.1, 100)
        self.dspin_cutoff.setValue(self.config["cutoff_freq"])
        form.addRow("Frec. corte (Hz):", self.dspin_cutoff)
        self.dspin_fs = QDoubleSpinBox()
        self.dspin_fs.setRange(1, 1000)
        self.dspin_fs.setValue(self.config["sampling_frequency"])
        form.addRow("Frec. muestreo (Hz):", self.dspin_fs)
        g1.setLayout(form)
        layout.addWidget(g1)

        g2 = QGroupBox("Umbrales de detección")
        form2 = QFormLayout()
        self.dspin_brake = QDoubleSpinBox()
        self.dspin_brake.setRange(0, 10)
        self.dspin_brake.setValue(self.config["brake_threshold"])
        form2.addRow("Umbral freno:", self.dspin_brake)
        self.dspin_throttle = QDoubleSpinBox()
        self.dspin_throttle.setRange(0, 10)
        self.dspin_throttle.setValue(self.config["throttle_threshold"])
        form2.addRow("Umbral acelerador:", self.dspin_throttle)
        self.dspin_mad = QDoubleSpinBox()
        self.dspin_mad.setRange(1, 10)
        self.dspin_mad.setValue(self.config["outlier_mad_threshold"])
        form2.addRow("Umbral MAD:", self.dspin_mad)
        self.spin_percentile = QSpinBox()
        self.spin_percentile.setRange(80, 100)
        self.spin_percentile.setValue(self.config["gg_percentile"])
        form2.addRow("Percentil G-G:", self.spin_percentile)
        g2.setLayout(form2)
        layout.addWidget(g2)

        btn_update = QPushButton("Actualizar configuración")
        btn_update.clicked.connect(self.update_config)
        layout.addWidget(btn_update)
        layout.addStretch()

    def setup_signals_tab(self):
        tab = QWidget()
        self.tabs.addTab(tab, "📡 Señales")
        layout = QVBoxLayout(tab)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Canal:"))
        self.cmb_channel = QComboBox()
        self.cmb_channel.addItem("Seleccione un canal...", None)
        self.cmb_channel.currentIndexChanged.connect(self.plot_signals)
        controls.addWidget(self.cmb_channel)
        self.chk_filtered = QCheckBox("Mostrar señal filtrada")
        self.chk_filtered.setChecked(True)
        self.chk_filtered.stateChanged.connect(self.plot_signals)
        controls.addWidget(self.chk_filtered)
        self.chk_events = QCheckBox("Mostrar eventos")
        self.chk_events.setChecked(True)
        self.chk_events.stateChanged.connect(self.plot_signals)
        controls.addWidget(self.chk_events)
        controls.addStretch()
        layout.addLayout(controls)
        self.signals_canvas = MplCanvas(self, width=8, height=6, dpi=100)
        toolbar = NavigationToolbar(self.signals_canvas, self)
        layout.addWidget(toolbar)
        layout.addWidget(self.signals_canvas)

    def setup_gg_tab(self):
        """Pestaña G-G con botón para abrir en ventana independiente y vista reducida."""
        tab = QWidget()
        self.tabs.addTab(tab, "📐 Diagrama G-G")
        layout = QVBoxLayout(tab)

        # Botón para abrir ventana externa
        btn_open = QPushButton("Abrir en ventana independiente")
        btn_open.clicked.connect(self.open_gg_window)
        layout.addWidget(btn_open)

        # Vista simplificada en la pestaña (solo el canvas con controles mínimos)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Unidades:"))
        self.cmb_gg_units = QComboBox()
        self.cmb_gg_units.addItems(["G", "m/s2"])
        self.cmb_gg_units.setCurrentText(self.config["axis_units"])
        self.cmb_gg_units.currentTextChanged.connect(self.plot_gg)
        controls.addWidget(self.cmb_gg_units)

        controls.addWidget(QLabel("Envolvente:"))
        self.cmb_envelope = QComboBox()
        self.cmb_envelope.addItems(["Ninguna", "Convex Hull", "Percentil robusto"])
        self.cmb_envelope.setCurrentIndex(2)
        self.cmb_envelope.currentTextChanged.connect(self.plot_gg)
        controls.addWidget(self.cmb_envelope)
        controls.addStretch()
        layout.addLayout(controls)

        self.gg_canvas = MplCanvas(self, width=5, height=5, dpi=100)
        toolbar = NavigationToolbar(self.gg_canvas, self)
        layout.addWidget(toolbar)
        layout.addWidget(self.gg_canvas)

    def open_gg_window(self):
        """Abre una nueva ventana con el diagrama G-G ampliado."""
        if self.processed_data is None:
            QMessageBox.information(self, "Sin datos", "Primero cargue un archivo o ejecute el análisis.")
            return
        win = GGWindow(self)
        self.gg_windows.append(win)
        win.destroyed.connect(lambda: self.gg_windows.remove(win) if win in self.gg_windows else None)
        win.show()
        win.update_plot()

    # Método común de dibujo G-G usado por la pestaña y la ventana independiente
    def _plot_gg_in_canvas(self, canvas, units, envelope, update_func=None):
        """Dibuja el diagrama G-G en el canvas proporcionado.
        update_func es una callback (metrics, centroid_shift) para actualizar widgets externos."""
        if self.processed_data is None:
            return
        if "accel_x" not in self.processed_data.columns or "accel_y" not in self.processed_data.columns:
            canvas.axes.clear()
            canvas.axes.text(0.5, 0.5, "Se requieren accel_x y accel_y",
                             ha='center', va='center', color=C("text_w"),
                             transform=canvas.axes.transAxes)
            canvas.draw()
            return

        df = self.processed_data
        ax_col = "accel_x_filtered" if "accel_x_filtered" in df.columns else "accel_x"
        ay_col = "accel_y_filtered" if "accel_y_filtered" in df.columns else "accel_y"
        ax_raw = df[ax_col].values
        ay_raw = df[ay_col].values
        time_raw = df["time"].values
        ax = pd.Series(ax_raw).interpolate().bfill().ffill().values
        ay = pd.Series(ay_raw).interpolate().bfill().ffill().values
        time_arr = time_raw.copy()
        if units.lower() == "m/s2":
            g_conv = self.config["g_conversion"]
            ax = ax / g_conv
            ay = ay / g_conv
        lateral_g = ay
        longitudinal_g = ax
        valid = np.isfinite(lateral_g) & np.isfinite(longitudinal_g)
        if not valid.any():
            canvas.axes.clear()
            canvas.axes.text(0.5, 0.5, "No hay datos válidos",
                             ha='center', va='center', color=C("text_w"),
                             transform=canvas.axes.transAxes)
            canvas.draw()
            return
        lateral_g = lateral_g[valid]
        longitudinal_g = longitudinal_g[valid]
        time_valid = time_arr[valid] if len(time_arr) == len(lateral_g) else np.arange(len(lateral_g))

        percentile = self.config["gg_percentile"]
        metrics = compute_gg_metrics(lateral_g, longitudinal_g, time_valid, percentile)
        centroid_lat = np.mean(lateral_g)
        centroid_lon = np.mean(longitudinal_g)
        centroid_shift = np.sqrt(centroid_lat**2 + centroid_lon**2)

        PURE_THRESHOLD = 0.15
        labels, color_map = classify_gg_regions(lateral_g, longitudinal_g, PURE_THRESHOLD)

        MAX_POINTS = 15000
        n_points = len(lateral_g)
        if n_points > MAX_POINTS:
            idx = np.random.choice(n_points, MAX_POINTS, replace=False)
            lat_plot = lateral_g[idx]
            lon_plot = longitudinal_g[idx]
            labels_plot = labels[idx]
        else:
            lat_plot = lateral_g
            lon_plot = longitudinal_g
            labels_plot = labels

        canvas.axes.clear()
        ax_obj = canvas.axes
        ax_obj.set_facecolor(C("bg1"))
        ax_obj.tick_params(colors=C("text_w"))
        for spine in ax_obj.spines.values():
            spine.set_color(C("text_w"))

        unique_labels = sorted(set(labels_plot))
        if "Near Origin" in unique_labels:
            unique_labels.remove("Near Origin")
            unique_labels.append("Near Origin")

        for lbl in unique_labels:
            mask = labels_plot == lbl
            if not mask.any():
                continue
            color = color_map.get(lbl, "gray")
            legend_name = GG_LABELS_ES.get(lbl, lbl)
            ax_obj.scatter(lat_plot[mask], lon_plot[mask],
                           s=3, color=color, alpha=0.5, label=legend_name, edgecolors='none')

        if envelope == "Convex Hull":
            try:
                mag = np.sqrt(lat_plot**2 + lon_plot**2)
                mask_env = np.isfinite(lat_plot) & np.isfinite(lon_plot) & (mag > 0.01)
                points = np.column_stack([lat_plot[mask_env], lon_plot[mask_env]])
                if len(points) >= 4:
                    hull = ConvexHull(points)
                    for simplex in hull.simplices:
                        ax_obj.plot(points[simplex, 0], points[simplex, 1],
                                    color=C("gold"), linewidth=2, alpha=0.8)
            except Exception:
                pass
        elif envelope == "Percentil robusto":
            env_points = compute_gg_envelope(lateral_g, longitudinal_g,
                                             n_bins=72, percentile=percentile,
                                             smooth_factor=0.5)
            if env_points is not None and len(env_points) > 0:
                ax_obj.plot(env_points[:, 0], env_points[:, 1],
                            color=C("cyan"), linewidth=2, alpha=0.9, label="Envolvente robusta")
                ax_obj.fill(env_points[:, 0], env_points[:, 1],
                            color=C("cyan"), alpha=0.1)

        ax_obj.axhline(0, color='gray', linestyle='--', alpha=0.5)
        ax_obj.axvline(0, color='gray', linestyle='--', alpha=0.5)
        ax_obj.set_xlabel("Aceleración lateral (G)", color=C("text_w"))
        ax_obj.set_ylabel("Aceleración longitudinal (G)", color=C("text_w"))
        ax_obj.set_title("Diagrama G-G — Envolvente de fricción del vehículo", color=C("text_w"), fontweight='bold')
        ax_obj.set_aspect('equal', adjustable='box')
        ax_obj.grid(True, alpha=0.3, color=C("text_g"))

        xlim = ax_obj.get_xlim()
        ylim = ax_obj.get_ylim()
        ax_obj.text(xlim[0], 0, '← Curva derecha', va='center', ha='left',
                    color=C("text_g"), fontsize=9, alpha=0.7)
        ax_obj.text(xlim[1], 0, 'Curva izquierda →', va='center', ha='right',
                    color=C("text_g"), fontsize=9, alpha=0.7)
        ax_obj.text(0, ylim[1], '↑ Aceleración', ha='center', va='bottom',
                    color=C("text_g"), fontsize=9, alpha=0.7)
        ax_obj.text(0, ylim[0], '↓ Frenado', ha='center', va='top',
                    color=C("text_g"), fontsize=9, alpha=0.7)

        ax_obj.legend(loc='upper right', fontsize=7, markerscale=2,
                      facecolor=C("bg2"), edgecolor=C("border"),
                      labelcolor=C("text_w"), framealpha=0.9)

        canvas.fig.tight_layout()
        canvas.draw()

        if update_func:
            update_func(metrics, centroid_shift)

    def plot_gg(self):
        """Actualiza el diagrama en la pestaña G-G."""
        if self.processed_data is None:
            return
        self._plot_gg_in_canvas(
            canvas=self.gg_canvas,
            units=self.cmb_gg_units.currentText(),
            envelope=self.cmb_envelope.currentText()
        )
        # También actualizar ventanas independientes
        for win in self.gg_windows:
            try:
                win.update_plot()
            except Exception:
                pass

    def plot_signals(self):
        if self.processed_data is None:
            return
        canvas = self.signals_canvas
        canvas.axes.clear()
        idx = self.cmb_channel.currentIndex()
        if idx <= 0:
            canvas.axes.text(0.5, 0.5, "Seleccione un canal", ha='center', va='center',
                             color=C("text_w"), transform=canvas.axes.transAxes)
            canvas.draw()
            return
        channel = self.cmb_channel.itemData(idx)
        if channel is None or channel not in self.processed_data.columns:
            canvas.axes.text(0.5, 0.5, "Canal no disponible", ha='center', va='center',
                             color=C("text_w"), transform=canvas.axes.transAxes)
            canvas.draw()
            return

        df = self.processed_data
        t = df["time"]
        raw = df[channel]
        max_plot_points = 10000
        step = max(1, len(df) // max_plot_points)
        t_plot = t.iloc[::step]
        raw_plot = raw.iloc[::step]

        canvas.axes.plot(t_plot, raw_plot, label="Señal original", color=C("red"), linewidth=1.5)

        if self.chk_filtered.isChecked() and f"{channel}_filtered" in df.columns:
            filt = df[f"{channel}_filtered"]
            filt_plot = filt.iloc[::step]
            removed_plot = raw_plot.values - filt_plot.values
            canvas.axes.plot(t_plot, filt_plot, label="Señal filtrada", color=C("cyan"), linewidth=2, alpha=0.8)
            canvas.axes.plot(t_plot, removed_plot, label="Componente eliminada", color=C("gold"), linewidth=1, alpha=0.6)

        if self.chk_events.isChecked() and len(self.event_registry) > 0:
            max_event_overlays = 200
            shown = 0
            t_min = float(t.iloc[0])
            t_max = float(t.iloc[-1])
            for event in self.event_registry.events:
                if shown >= max_event_overlays:
                    break
                if channel not in event.channels:
                    continue
                if event.start_time < t_min or event.end_time > t_max:
                    continue
                canvas.axes.axvspan(event.start_time, event.end_time, alpha=0.2, color=C("red"))
                shown += 1

        channel_display = CHANNEL_TRANSLATIONS.get(channel, channel)
        canvas.axes.set_title(f"Análisis de señal — {channel_display}", color=C("text_w"), fontweight='bold')
        canvas.axes.set_xlabel("Tiempo (s)", color=C("text_w"))
        canvas.axes.set_ylabel("Valor", color=C("text_w"))
        canvas.axes.legend(loc='upper right')
        canvas.axes.grid(True, alpha=0.3)
        canvas.fig.tight_layout()
        canvas.draw()

    def setup_events_tab(self):
        tab = QWidget()
        self.tabs.addTab(tab, "⚠️ Eventos")
        layout = QVBoxLayout(tab)
        self.events_table = QTableWidget()
        self.events_table.setColumnCount(8)
        self.events_table.setHorizontalHeaderLabels(["ID", "Categoría", "Tipo de evento", "Severidad", "Canales", "Inicio (s)", "Fin (s)", "Duración (s)"])
        self.events_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.events_table)
        btn_export = QPushButton("Exportar eventos a CSV")
        btn_export.clicked.connect(self.export_events)
        layout.addWidget(btn_export)

    def setup_report_tab(self):
        tab = QWidget()
        self.tabs.addTab(tab, "📄 Informe")
        layout = QVBoxLayout(tab)
        self.report_text = QTextEdit()
        self.report_text.setReadOnly(True)
        layout.addWidget(self.report_text)
        btn_save = QPushButton("Guardar informe (TXT)")
        btn_save.clicked.connect(self.save_report)
        layout.addWidget(btn_save)

    def load_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar archivo", "",
            "Archivos soportados (*.csv *.xlsx);;CSV (*.csv);;Excel (*.xlsx)"
        )
        if file_path:
            self.load_data(file_path)

    def load_example(self):
        example_path = "data.xlsx"
        if os.path.exists(example_path):
            self.load_data(example_path)
        else:
            QMessageBox.warning(self, "Archivo no encontrado",
                                f"No se encontró '{example_path}' en el directorio actual.")

    def load_data(self, filepath):
        try:
            ext = Path(filepath).suffix.lower()
            if ext == ".csv":
                df = pd.read_csv(filepath)
            elif ext in [".xlsx", ".xls"]:
                df = pd.read_excel(filepath)
            else:
                QMessageBox.critical(self, "Error", "Formato no soportado.")
                return
        except Exception as e:
            QMessageBox.critical(self, "Error al leer", str(e))
            return
        if df.empty:
            QMessageBox.critical(self, "Error", "El archivo está vacío.")
            return

        self.raw_data = df.copy()
        n = len(df)
        t = np.arange(n) / self.config["sampling_frequency"]
        processed = df.copy()
        processed["time"] = t
        self.processed_data = processed

        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        self.metadata = {
            "num_samples": n,
            "num_columns": len(df.columns),
            "available_channels": numeric_cols,
            "sampling_frequency": self.config["sampling_frequency"],
            "duration_seconds": n / self.config["sampling_frequency"],
            "file_name": Path(filepath).name,
        }
        self.event_registry.clear()
        self.btn_analyze.setEnabled(True)
        self.status_label.setText(f"Cargado: {Path(filepath).name} ({n} muestras)")

        self.cmb_channel.clear()
        self.cmb_channel.addItem("Seleccione un canal...", None)
        for col in numeric_cols:
            display_name = CHANNEL_TRANSLATIONS.get(col, col)
            self.cmb_channel.addItem(display_name, col)
        if numeric_cols:
            self.cmb_channel.setCurrentIndex(1)
            self.plot_signals()
            self.plot_gg()

    def update_config(self):
        self.config["sampling_frequency"] = self.dspin_fs.value()
        self.config["filter_type"] = self.cmb_filter.currentText()
        self.config["filter_order"] = self.spin_order.value()
        self.config["cutoff_freq"] = self.dspin_cutoff.value()
        self.config["brake_threshold"] = self.dspin_brake.value()
        self.config["throttle_threshold"] = self.dspin_throttle.value()
        self.config["outlier_mad_threshold"] = self.dspin_mad.value()
        self.config["gg_percentile"] = self.spin_percentile.value()
        self.config["axis_units"] = self.cmb_gg_units.currentText()
        self.status_label.setText("Configuración actualizada.")
        if self.processed_data is not None:
            self.plot_signals()
            self.plot_gg()

    def run_analysis(self):
        if self.raw_data is None:
            QMessageBox.warning(self, "Sin datos", "Primero cargue un archivo.")
            return
        if getattr(self, "analysis_thread", None) is not None and self.analysis_thread.isRunning():
            QMessageBox.information(self, "Análisis en curso", "Ya hay un análisis ejecutándose.")
            return

        self.btn_analyze.setEnabled(False)
        self.btn_load.setEnabled(False)
        self.btn_example.setEnabled(False)
        self.status_label.setText("Analizando...")

        self.progress = QProgressDialog("Analizando datos...", "", 0, 0, self)
        self.progress.setWindowModality(Qt.WindowModal)
        self.progress.setCancelButton(None)
        self.progress.show()

        analysis_input = self.raw_data.copy()
        fs = float(self.config["sampling_frequency"])
        analysis_input["time"] = np.arange(len(analysis_input)) / fs

        self.analysis_thread = AnalysisThread(analysis_input, self.config.copy())
        self.analysis_thread.result_ready.connect(self.analysis_finished)
        self.analysis_thread.error.connect(self.analysis_error)
        self.analysis_thread.finished.connect(self.analysis_thread_ended)
        self.analysis_thread.start()

    def analysis_thread_ended(self):
        self.btn_analyze.setEnabled(self.raw_data is not None)
        self.btn_load.setEnabled(True)
        self.btn_example.setEnabled(True)
        if self.analysis_thread is not None:
            self.analysis_thread.deleteLater()
            self.analysis_thread = None

    def analysis_finished(self, df_out, events):
        try:
            if hasattr(self, "progress"):
                self.progress.close()
            self.processed_data = df_out
            self.metadata["sampling_frequency"] = self.config["sampling_frequency"]
            self.metadata["duration_seconds"] = len(df_out) / self.config["sampling_frequency"]
            self.event_registry.clear()
            self.event_registry.add_events(events)
            self.status_label.setText(f"Análisis completado. Eventos: {len(events)}")

            for name, func in [
                ("gráfica de señales", self.plot_signals),
                ("diagrama G-G", self.plot_gg),
                ("tabla de eventos", self.update_events_table),
                ("informe", self.update_report),
            ]:
                try:
                    func()
                except Exception:
                    logging.exception("Error actualizando %s", name)
            QMessageBox.information(
                self, "Análisis completado",
                f"Se detectaron {len(events)} anomalías.\n"
                f"Críticas: {self.event_registry.get_summary()['critical_count']}"
            )
        except Exception:
            logging.exception("Error en analysis_finished")
            self.status_label.setText("El análisis terminó, pero ocurrió un error de interfaz.")

    def analysis_error(self, err_msg):
        try:
            if hasattr(self, "progress"):
                self.progress.close()
            logging.error("Error en hilo de análisis:\n%s", err_msg)
            self.status_label.setText("Error en análisis.")
            QMessageBox.critical(self, "Error", err_msg + f"\n\nEl detalle también fue guardado en:\n{LOG_FILE}")
        except Exception:
            logging.exception("Error mostrando analysis_error")

    def update_events_table(self):
        df_ev = self.event_registry.to_dataframe()
        table = self.events_table
        table.setColumnCount(8)
        table.setHorizontalHeaderLabels(["ID", "Categoría", "Tipo de evento", "Severidad", "Canales", "Inicio (s)", "Fin (s)", "Duración (s)"])

        if not df_ev.empty:
            # Mapear severidad a orden
            df_ev['sev_order'] = df_ev['severity'].map(SEVERITY_ORDER).fillna(99)
            df_ev = df_ev.sort_values('sev_order').reset_index(drop=True)
            df_ev = df_ev.drop(columns='sev_order')

        max_table_rows = 1000
        df_show = df_ev.head(max_table_rows)
        table.setRowCount(len(df_show))

        for i, (_, row) in enumerate(df_show.iterrows()):
            table.setItem(i, 0, QTableWidgetItem(str(row['id'])))
            cat_es = CATEGORY_ES.get(row['category'], row['category'])
            table.setItem(i, 1, QTableWidgetItem(cat_es))
            tipo_es = TYPE_ES.get(row['type'], row['type'])
            table.setItem(i, 2, QTableWidgetItem(tipo_es))
            sev_es = SEVERITY_ES.get(row['severity'], row['severity'])
            table.setItem(i, 3, QTableWidgetItem(sev_es))
            canales = row['channels'].split(', ')
            canales_es = ', '.join([CHANNEL_TRANSLATIONS.get(c, c) for c in canales])
            table.setItem(i, 4, QTableWidgetItem(canales_es))
            table.setItem(i, 5, QTableWidgetItem(f"{row['start_time']:.3f}"))
            table.setItem(i, 6, QTableWidgetItem(f"{row['end_time']:.3f}"))
            table.setItem(i, 7, QTableWidgetItem(f"{row['duration']:.3f}"))

            sev = row['severity']
            if sev == "Crítico":
                color = C("critical")
            elif sev == "Advertencia":
                color = C("gold")
            else:
                color = None
            if color:
                for j in range(8):
                    item = table.item(i, j)
                    if item:
                        item.setBackground(QColor(color))

        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        if len(df_ev) > max_table_rows:
            self.status_label.setText(
                f"Análisis completado. Eventos: {len(df_ev)} "
                f"(tabla mostrando los primeros {max_table_rows})"
            )

    def update_report(self):
        if self.raw_data is None:
            return
        report = generate_report(self.raw_data, self.processed_data, self.metadata,
                                 self.event_registry, self.config)
        self.report_text.setText(report)

    def export_events(self):
        if len(self.event_registry) == 0:
            QMessageBox.information(self, "Sin eventos", "No hay eventos para exportar.")
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "Guardar eventos", "eventos.csv", "CSV (*.csv)")
        if file_path:
            df_ev = self.event_registry.to_dataframe()
            df_ev.to_csv(file_path, index=False)
            QMessageBox.information(self, "Exportado", f"Eventos guardados en {file_path}")

    def save_report(self):
        if self.raw_data is None:
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "Guardar informe", "informe.txt", "TXT (*.txt)")
        if file_path:
            report = generate_report(self.raw_data, self.processed_data, self.metadata,
                                     self.event_registry, self.config)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(report)
            QMessageBox.information(self, "Guardado", f"Informe guardado en {file_path}")

# =============================================================================
# EJECUCIÓN
# =============================================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont(FONT, 10))
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())