# Actividad 2: Diagnóstico de telemetría

## Objetivo

Procesar y auditar un archivo de telemetría de un vehículo Fórmula SAE para detectar ruido, pérdida de señal, saturación de sensores y eventos de seguridad.

## Archivo de entrada

- Ruta esperada: `datos/data.csv`
- Frecuencia de muestreo asumida: **100 Hz**.
- Canales principales:
  - `accel_x`
  - `accel_y`
  - `speed_kmph`
  - `brake_pressure`
  - `throttle`

## Procesamiento

El notebook `notebook/diagnostico_telemetria.ipynb` y el módulo `src/telemetria.py` implementan:

1. Carga y verificación de CSV.
2. Revisión de tipos de datos y valores faltantes.
3. Creación del vector de tiempo.
4. Filtro pasa-bajas con filtrado de fase cero (`filtfilt`) para evitar retardo.
5. Comparación de señales crudas vs filtradas.
6. Cálculo de magnitud combinada:

   \(|G| = \sqrt{accel_x^2 + accel_y^2}\)

7. Cálculo de fuerza G máxima sobre señal filtrada.
8. Generación de diagrama G-G.
9. Análisis de asimetrías direccionales.
10. Detección de pérdida sostenida de señal inercial.
11. Detección de freno y acelerador simultáneos con persistencia mínima de 100 ms.
12. Reporte de timestamp de cada evento.

## Resultados

Guardar resultados en `resultados/`:

- `señales_filtradas.png`
- `diagrama_gg.png`
- `fallas_detectadas.csv`
- `reporte_tecnico.md`

## Reproducibilidad

1. Crear entorno virtual de Python.
2. Instalar dependencias desde `requirements.txt`.
3. Ejecutar notebook y/o script para procesar `datos/data.csv`.

> AGREGAR_RESULTADOS_EXPERIMENTALES
