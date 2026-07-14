from __future__ import annotations

from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.signal import butter, filtfilt

SAMPLE_RATE_HZ = 100.0
PERSISTENCE_MS = 100
PERSISTENCE_SAMPLES = int((PERSISTENCE_MS / 1000.0) * SAMPLE_RATE_HZ)
REQUIRED_COLUMNS = ["accel_x", "accel_y", "speed_kmph", "brake_pressure", "throttle"]


class TelemetryError(Exception):
    """Error de validación o procesamiento de telemetría."""


def load_telemetry(csv_path: str | Path) -> pd.DataFrame:
    path = Path(csv_path)
    if not path.exists():
        raise TelemetryError(f"No se encontró el archivo: {path}")

    df = pd.read_csv(path)
    missing_columns = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_columns:
        raise TelemetryError(f"Faltan columnas requeridas: {missing_columns}")

    return df


def validate_dataframe(df: pd.DataFrame) -> dict[str, object]:
    null_counts = df[REQUIRED_COLUMNS].isna().sum().to_dict()
    dtypes = df[REQUIRED_COLUMNS].dtypes.astype(str).to_dict()

    return {"null_counts": null_counts, "dtypes": dtypes}


def add_time_vector(df: pd.DataFrame, fs_hz: float = SAMPLE_RATE_HZ) -> pd.DataFrame:
    output = df.copy()
    dt = 1.0 / fs_hz
    output["time_s"] = np.arange(len(output), dtype=float) * dt
    return output


def low_pass_filter(signal_data: np.ndarray, fs_hz: float, cutoff_hz: float, order: int = 2) -> np.ndarray:
    nyquist = fs_hz / 2.0
    normalized_cutoff = cutoff_hz / nyquist
    b, a = butter(order, normalized_cutoff, btype="low")
    return filtfilt(b, a, signal_data)


def apply_filters(df: pd.DataFrame, fs_hz: float = SAMPLE_RATE_HZ, cutoff_hz: float = 10.0) -> pd.DataFrame:
    output = df.copy()
    for channel in ["accel_x", "accel_y", "speed_kmph", "brake_pressure", "throttle"]:
        output[f"{channel}_filtered"] = low_pass_filter(output[channel].to_numpy(), fs_hz, cutoff_hz)
    return output


def calculate_g_magnitude(df: pd.DataFrame) -> pd.Series:
    gx = df["accel_x_filtered"]
    gy = df["accel_y_filtered"]
    return np.sqrt(gx**2 + gy**2)


def max_g_force(df: pd.DataFrame) -> float:
    g_mag = calculate_g_magnitude(df)
    return float(g_mag.max()) if not g_mag.empty else float("nan")


def _find_persistent_regions(mask: Iterable[bool], min_samples: int) -> list[tuple[int, int]]:
    regions: list[tuple[int, int]] = []
    start_idx: int | None = None

    for i, active in enumerate(mask):
        if active and start_idx is None:
            start_idx = i
        elif not active and start_idx is not None:
            if i - start_idx >= min_samples:
                regions.append((start_idx, i - 1))
            start_idx = None

    if start_idx is not None:
        end_idx = len(list(mask)) - 1
        if end_idx - start_idx + 1 >= min_samples:
            regions.append((start_idx, end_idx))

    return regions


def detect_inertial_signal_loss(df: pd.DataFrame, threshold_g: float = 0.02) -> pd.DataFrame:
    g_mag = calculate_g_magnitude(df)
    mask = (g_mag <= threshold_g).to_numpy()
    regions = _find_persistent_regions(mask, PERSISTENCE_SAMPLES)

    events = []
    for start, end in regions:
        events.append(
            {
                "event": "inertial_signal_loss",
                "start_time_s": float(df.iloc[start]["time_s"]),
                "end_time_s": float(df.iloc[end]["time_s"]),
                "duration_s": float(df.iloc[end]["time_s"] - df.iloc[start]["time_s"]),
                "details": f"|G| <= {threshold_g}",
            }
        )

    return pd.DataFrame(events)


def detect_brake_throttle_overlap(
    df: pd.DataFrame,
    brake_threshold: float = 0.2,
    throttle_threshold: float = 0.2,
) -> pd.DataFrame:
    mask = ((df["brake_pressure_filtered"] >= brake_threshold) & (df["throttle_filtered"] >= throttle_threshold)).to_numpy()
    regions = _find_persistent_regions(mask, PERSISTENCE_SAMPLES)

    events = []
    for start, end in regions:
        events.append(
            {
                "event": "brake_throttle_overlap",
                "start_time_s": float(df.iloc[start]["time_s"]),
                "end_time_s": float(df.iloc[end]["time_s"]),
                "duration_s": float(df.iloc[end]["time_s"] - df.iloc[start]["time_s"]),
                "details": "brake_pressure & throttle simultáneos",
            }
        )

    return pd.DataFrame(events)


def save_plots(df: pd.DataFrame, output_dir: str | Path) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    fig1, ax1 = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    ax1[0].plot(df["time_s"], df["accel_x"], label="accel_x cruda", alpha=0.6)
    ax1[0].plot(df["time_s"], df["accel_x_filtered"], label="accel_x filtrada", linewidth=2)
    ax1[0].plot(df["time_s"], df["accel_y"], label="accel_y cruda", alpha=0.6)
    ax1[0].plot(df["time_s"], df["accel_y_filtered"], label="accel_y filtrada", linewidth=2)
    ax1[0].set_ylabel("Aceleración [g]")
    ax1[0].legend()
    ax1[0].grid(True, alpha=0.3)

    ax1[1].plot(df["time_s"], df["brake_pressure"], label="brake_pressure cruda", alpha=0.6)
    ax1[1].plot(df["time_s"], df["brake_pressure_filtered"], label="brake_pressure filtrada", linewidth=2)
    ax1[1].plot(df["time_s"], df["throttle"], label="throttle cruda", alpha=0.6)
    ax1[1].plot(df["time_s"], df["throttle_filtered"], label="throttle filtrada", linewidth=2)
    ax1[1].set_xlabel("Tiempo [s]")
    ax1[1].set_ylabel("Señal normalizada")
    ax1[1].legend()
    ax1[1].grid(True, alpha=0.3)

    fig1.tight_layout()
    fig1.savefig(out / "señales_filtradas.png", dpi=150)
    plt.close(fig1)

    fig2, ax2 = plt.subplots(figsize=(6, 6))
    ax2.scatter(df["accel_x_filtered"], df["accel_y_filtered"], s=8, alpha=0.6)
    ax2.set_xlabel("accel_x filtrada [g]")
    ax2.set_ylabel("accel_y filtrada [g]")
    ax2.set_title("Diagrama G-G")
    ax2.grid(True, alpha=0.3)
    fig2.tight_layout()
    fig2.savefig(out / "diagrama_gg.png", dpi=150)
    plt.close(fig2)


def run_analysis(
    input_csv: str | Path = "datos/data.csv",
    output_dir: str | Path = "resultados",
) -> dict[str, object]:
    df = load_telemetry(input_csv)
    quality = validate_dataframe(df)
    df = add_time_vector(df)

    if len(df) < 20:
        raise TelemetryError("Se requieren al menos 20 muestras para filtrar con estabilidad numérica.")

    df = apply_filters(df)
    df["g_magnitude"] = calculate_g_magnitude(df)

    inertial_loss = detect_inertial_signal_loss(df)
    overlap = detect_brake_throttle_overlap(df)

    events = pd.concat([inertial_loss, overlap], ignore_index=True)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    events.to_csv(out / "fallas_detectadas.csv", index=False)
    save_plots(df, out)

    return {
        "quality": quality,
        "max_g": max_g_force(df),
        "events": events,
    }


if __name__ == "__main__":
    results = run_analysis(
        input_csv=Path(__file__).resolve().parents[1] / "datos" / "data.csv",
        output_dir=Path(__file__).resolve().parents[1] / "resultados",
    )
    print("Análisis completado")
    print(f"Máximo |G| filtrado: {results['max_g']:.3f}")
    print(results["events"])
