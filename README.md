# Data Acquisition – Actividades de Reclutamiento

Este repositorio contiene el desarrollo y la documentación de dos actividades enfocadas en **adquisición de datos (DAQ), procesamiento de señales, validación de sensores y seguridad aplicada a un vehículo Formula SAE**.

Los proyectos abarcan desde la adquisición de señales mediante un microcontrolador **ESP32** hasta el procesamiento y análisis de registros de telemetría mediante **Python**, incluyendo herramientas de visualización, detección de anomalías y generación de reportes técnicos.

---

## Actividad 1 – Sistema de Validación de Plausibilidad APPS

Desarrollo de un sistema de seguridad para validar las señales redundantes del **Accelerator Pedal Position Sensor (APPS)**.

El sistema utiliza dos canales de medición independientes con rangos eléctricos asimétricos que representan la posición del pedal del acelerador. Las señales son adquiridas y procesadas mediante una **ESP32**, normalizando ambos sensores a una escala común para comparar su comportamiento.

El sistema permite:

- Adquirir dos señales APPS independientes.
- Trabajar con rangos eléctricos asimétricos.
- Normalizar ambas señales a una escala común.
- Detectar discrepancias o condiciones de falla entre los sensores.
- Aplicar una persistencia temporal de **100 ms** antes de declarar una falla.
- Generar una señal de interrupción ante una condición crítica.
- Monitorear las señales mediante comunicación serial.
- Visualizar los datos mediante un dashboard.

El repositorio incluye el **código del microcontrolador**, documentación del sistema, esquemático electrónico, enlace de simulación y capturas del dashboard.

---

## Actividad 2 – Diagnóstico de Telemetría y Detección de Anomalías

Desarrollo de un pipeline de análisis en **Python** para procesar y auditar un registro de telemetría de un vehículo Formula SAE.

El análisis trabaja con señales adquiridas a una frecuencia de muestreo de **100 Hz**, incluyendo datos de aceleración, velocidad, presión de freno y posición del acelerador.

El procesamiento realizado incluye:

- Lectura y procesamiento del archivo de telemetría.
- Acondicionamiento de señales mediante filtrado pasa-bajas.
- Filtrado de fase cero para evitar retrasos temporales.
- Cálculo de la magnitud de aceleración G combinada.
- Generación y análisis del **Diagrama G-G**.
- Identificación de asimetrías en la envolvente de cargas.
- Detección de pérdida o caída de señal del sensor inercial.
- Detección de eventos de plausibilidad entre freno y acelerador.
- Aplicación de una persistencia temporal de **100 ms** para evitar falsos positivos.
- Identificación de los timestamps correspondientes a las anomalías.
- Visualización de resultados mediante gráficas y dashboard.
- Generación de un reporte técnico con conclusiones y acciones recomendadas.

El análisis se encuentra documentado mediante un **Jupyter Notebook**, scripts de Python, gráficas y capturas del dashboard.

---

## Contenido del repositorio

El repositorio contiene los principales entregables de ambas actividades:

- Código de validación APPS para ESP32.
- Esquemático del sistema de validación.
- Documentación técnica del sistema APPS.
- Enlace a la simulación del circuito.
- Dashboard de visualización APPS.
- Script de análisis de telemetría en Python.
- Jupyter Notebook con el procesamiento y análisis de datos.
- Dashboard para exploración de los datos de telemetría.
- Reportes técnicos y capturas de resultados.

---

## Tecnologías utilizadas

- ESP32 DevKitC / ESP32
- C / C++
- Python
- Jupyter Notebook
- Pandas
- NumPy
- SciPy
- Matplotlib
-LaTex
-
## Software utilizado
- Altium designer
- Thinkercad
- Arduino IDE
- Visual studio code
- Google COllab

## Inteligencia artificial utilizada

- Open AI
- DeepSeek

## Objetivo

El objetivo general de las actividades es desarrollar competencias relacionadas con **Data Acquisition (DAQ)** en Formula SAE, abarcando tanto la adquisición y validación de señales en tiempo real como el procesamiento posterior de datos para detectar fallas de instrumentación, anomalías y posibles violaciones de seguridad.

De esta forma, el repositorio integra el flujo completo de trabajo de un sistema DAQ: **adquisición, acondicionamiento, validación, procesamiento, diagnóstico y visualización de datos**.
