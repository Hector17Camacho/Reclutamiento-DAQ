# Actividades de Reclutamiento DAQ – Fórmula SAE

Este repositorio concentra dos actividades técnicas orientadas a **Data Acquisition (DAQ)** para un vehículo Fórmula SAE. El contenido cubre diseño e implementación de validación de sensores redundantes, seguridad electrónica, análisis de señales y diagnóstico de telemetría para detección de anomalías.

## Tabla de actividades

| Actividad | Descripción | Ruta |
|---|---|---|
| Actividad 1 | Sistema de validación de plausibilidad APPS con ESP32 | `actividad-1-apps/` |
| Actividad 2 | Diagnóstico de telemetría y detección de anomalías | `actividad-2-telemetria/` |

## Tecnologías utilizadas

- ESP32
- Arduino IDE
- C/C++
- Python
- Jupyter Notebook
- Pandas
- NumPy
- SciPy
- Matplotlib
- Simulador electrónico utilizado

## Navegación del repositorio

1. Revisar `actividad-1-apps/README.md` para el diseño del sistema APPS, el esquemático, la simulación y el código de control de seguridad.
2. Revisar `actividad-2-telemetria/README.md` para el flujo de auditoría de datos, notebook de análisis y generación de resultados.
3. Utilizar los archivos en `resultados/` como plantilla de entregables técnicos y completar los marcadores pendientes.

## Estructura

```text
formula-sae-daq-recruitment/
│
├── README.md
├── LICENSE
├── .gitignore
│
├── actividad-1-apps/
│   ├── README.md
│   ├── codigo/apps_esp32.ino
│   ├── esquematico/ESP32_APPS_Esquematico.pdf
│   ├── imagenes/
│   │   ├── circuito_fisico.jpg
│   │   ├── simulacion.png
│   │   └── monitor_serial.png
│   └── simulacion/enlace_simulacion.md
│
└── actividad-2-telemetria/
    ├── README.md
    ├── datos/data.csv
    ├── notebook/diagnostico_telemetria.ipynb
    ├── src/telemetria.py
    ├── resultados/
    │   ├── señales_filtradas.png
    │   ├── diagrama_gg.png
    │   ├── fallas_detectadas.csv
    │   └── reporte_tecnico.md
    └── requirements.txt
```

## Lista sugerida de commits (Conventional Commits)

- `feat(apps): add dual sensor ADC acquisition`
- `feat(safety): implement 100 ms plausibility timer`
- `feat(motor): add fail-safe motor disable output`
- `feat(telemetry): add zero-phase low-pass filter`
- `feat(analysis): generate G-G diagram`
- `fix(apps): correct sensor scaling`
- `docs(readme): add schematic and simulator link`
- `test(safety): validate persistent APPS fault`
- `chore(repo): add gitignore and requirements`

## Autor

**Héctor Enrique Camacho Duarte**
