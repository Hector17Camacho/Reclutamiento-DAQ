# Actividad 1: Sistema de plausibilidad APPS con ESP32

## Objetivo

Diseñar y validar un sistema electrónico de seguridad para el pedal de aceleración de un vehículo Fórmula SAE mediante dos sensores APPS redundantes.

## Descripción

Los sensores APPS se simulan con dos potenciómetros desplazados simultáneamente. Cada canal opera con un rango de voltaje distinto para habilitar redundancia y detección de fallas (cortocircuito, desconexión o señal no plausible).

El ESP32 implementa:

- Lectura de ambos canales por ADC.
- Conversión de lecturas a una escala común de 0 a 100 %.
- Escalado desacoplado de reglas de seguridad.
- Comparación continua entre porcentajes.
- Detección de diferencia no permitida.
- Mitigación de ruido transitorio.
- Confirmación de falla si persiste más de 100 ms.
- Activación de LED de alerta.
- Activación de señal de interrupción.
- Deshabilitación lógica del motor ante falla confirmada.

## Esquemático electrónico

- Archivo: [ESP32_APPS_Esquematico.pdf](esquematico/ESP32_APPS_Esquematico.pdf)
- Vista previa (agregar cuando esté disponible):

![Vista previa del esquemático](imagenes/simulacion.png)

## Circuito físico

![Circuito físico](imagenes/circuito_fisico.jpg)

> AGREGAR_FOTOGRAFIA_DEL_CIRCUITO

Descripción breve del montaje:

- **Alimentación:** fuente estable para ESP32 y red de sensores.
- **Potenciómetros:** dos canales APPS redundantes con recorridos calibrados.
- **Pines ADC del ESP32:** entradas dedicadas para APPS1 y APPS2.
- **Divisores resistivos:** adaptación de rango para entradas seguras del ADC.
- **Capacitores de filtrado:** reducción de ruido de alta frecuencia.
- **LED de alerta:** indicación visual de falla confirmada.
- **LED/salida de interrupción:** señal de estado de seguridad.
- **MOTOR_ENABLE:** señal lógica para habilitar/deshabilitar etapa de potencia externa.

## Simulación en línea

La simulación interactiva del circuito puede consultarse en:

[Ejecutar simulación](PEGAR_AQUI_EL_LINK_DEL_SIMULADOR)

![Simulación](imagenes/simulacion.png)

Adicionalmente, registrar evidencia del monitor serial:

![Monitor serial](imagenes/monitor_serial.png)

## Código del ESP32

Archivo principal: [`codigo/apps_esp32.ino`](codigo/apps_esp32.ino)

Funciones implementadas:

- `readSensors()`
- `convertToPercentage()`
- `checkPlausibility()`
- `updateFaultTimer()`
- `enableMotor()`
- `disableMotor()`
- `updateIndicators()`
- `printSerialData()`

Se utilizan constantes para:

- Pines ADC.
- Pin del LED de alerta.
- Pin de interrupción.
- Pin de habilitación del motor.
- Tiempo de persistencia de falla.
- Umbral máximo de diferencia.
- Valores mínimos y máximos de calibración de APPS1/APPS2.

## Lógica de control del motor

La lógica usa `millis()` de forma no bloqueante (sin `delay()` para confirmar la falla):

- En estado normal, `MOTOR_ENABLE` permanece activo.
- Si la diferencia excede el umbral, inicia temporizador de falla.
- Si vuelve a ser plausible antes de 100 ms, la falla se cancela.
- Si persiste más de 100 ms:
  - LED de alerta activo.
  - Señal de interrupción activa.
  - `MOTOR_ENABLE` desactivado.
  - Aceleración solicitada forzada a 0 %.

La salida `MOTOR_ENABLE` representa una señal lógica de seguridad y **no** debe conectarse directamente a un motor de potencia.

Ejemplo esperado en monitor serial (referencial):

```text
APPS1: 45.20 %
APPS2: 44.10 %
Diferencia: 1.10 %
Estado: PLAUSIBLE
Motor: HABILITADO
Interrupción: INACTIVA
```

En falla confirmada (referencial):

```text
APPS1: 72.30 %
APPS2: 35.80 %
Diferencia: 36.50 %
Estado: FALLA CONFIRMADA
Motor: DESHABILITADO
Interrupción: ACTIVA
```

## Calibración

La calibración se realiza registrando los valores ADC mínimo y máximo de cada potenciómetro en sus extremos mecánicos. Con esos límites, cada lectura se normaliza a 0–100 % mediante mapeo lineal y saturación por límites (`constrain`) para comparar ambos canales en escala común.

> AGREGAR_RESULTADOS_EXPERIMENTALES

## Evidencias

- Fotografía del circuito físico: `imagenes/circuito_fisico.jpg`
- Captura de simulación: `imagenes/simulacion.png`
- Captura de monitor serial: `imagenes/monitor_serial.png`
- Enlace al simulador: `simulacion/enlace_simulacion.md`
- Esquemático en PDF: `esquematico/ESP32_APPS_Esquematico.pdf`
