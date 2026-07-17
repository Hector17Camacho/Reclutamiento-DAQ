/*
 * ================================================================
 * SISTEMA DE VALIDACION DE PLAUSIBILIDAD APPS
 * ESP32 - WROOM-32D
 * ================================================================
 *
 * CALIBRACION FINAL MEDIDA (voltajes reales del sensor):
 *
 * APPS1:
 *   0.415 V = 0 %
 *   4.585 V = 100 %
 *
 * APPS2:
 *   1.251 V = 0 %
 *   3.749 V = 100 %
 *
 * Ambos sensores son crecientes.
 *
 * FUNCIONES:
 * - Lectura independiente APPS1 y APPS2
 * - Normalizacion de ambos a escala 0-100 %
 * - Deteccion de plausibilidad
 * - Tolerancia maxima: 10 %
 * - Persistencia de falla: 100 ms
 * - Deteccion de corto a GND
 * - Deteccion de corto a VCC
 * - Señal de interrupcion ante cortocircuito
 * - Desactivacion del motor ante falla confirmada
 * - LED verde = sistema OK
 * - LED rojo = falla confirmada
 * - Enclavamiento de falla
 * - RESET mediante Monitor Serial
 *
 * ================================================================
 */


// ================================================================
// PINES PARA ESP32
// ================================================================

#define PIN_APPS1          34     // ADC1_CH6 (solo entrada)
#define PIN_APPS2          35     // ADC1_CH7 (solo entrada)

#define PIN_INTERRUPCION   23     // Salida digital
#define PIN_MOTOR_ENABLE   22     // Salida digital

#define PIN_LED_ROJO       25     // Salida digital
#define PIN_LED_VERDE      26     // Salida digital


// ================================================================
// CONFIGURACION ELECTRICA (ESP32)
// ================================================================

// Voltaje de referencia del ADC (ESP32)
const float VOLTAJE_REF_ADC = 3.3;

// Resolución del ADC (12 bits)
const int RESOLUCION_ADC = 4095;


// ================================================================
// CALIBRACION FINAL MEDIDA
// ================================================================

// APPS1
const float APPS1_MIN_V = 0.415;
const float APPS1_MAX_V = 4.585;

// APPS2
const float APPS2_MIN_V = 1.251;
const float APPS2_MAX_V = 3.749;


// ================================================================
// LIMITES ELECTRICOS
// ================================================================

const float APPS1_LIM_INF = 0.25;
const float APPS1_LIM_SUP = 4.75;

const float APPS2_LIM_INF = 1.00;
const float APPS2_LIM_SUP = 4.00;


// ================================================================
// UMBRALES DE CORTOCIRCUITO
// ================================================================

const float UMBRAL_CORTO_GND = 0.10;
const float UMBRAL_CORTO_VCC = 4.90;


// ================================================================
// PLAUSIBILIDAD
// ================================================================

const float TOLERANCIA_PLAUSIBILIDAD = 10.0;

const unsigned long TIEMPO_CONFIRMACION_FALLA = 100;


// ================================================================
// TELEMETRIA
// ================================================================

const unsigned long INTERVALO_ENVIO = 100;

unsigned long tiempoUltimoEnvio = 0;


// ================================================================
// ESTADOS DEL SISTEMA
// ================================================================

enum EstadoSistema {

  ESTADO_OK,

  ESTADO_FALLA_PENDIENTE,

  ESTADO_FALLA_CONFIRMADA

};


EstadoSistema estadoSistema = ESTADO_OK;


// ================================================================
// TIPOS DE FALLA
// ================================================================

enum TipoFalla {

  FALLA_NINGUNA,

  FALLA_PLAUSIBILIDAD,

  FALLA_APPS1_FUERA_RANGO,

  FALLA_APPS2_FUERA_RANGO,

  FALLA_APPS1_CORTO_GND,

  FALLA_APPS1_CORTO_VCC,

  FALLA_APPS2_CORTO_GND,

  FALLA_APPS2_CORTO_VCC

};


TipoFalla tipoFallaActual =
  FALLA_NINGUNA;


TipoFalla tipoFallaEnclavada =
  FALLA_NINGUNA;


// ================================================================
// VARIABLES DE LOS SENSORES
// ================================================================

int apps1ADC = 0;
int apps2ADC = 0;


float apps1Voltaje = 0.0;
float apps2Voltaje = 0.0;


float apps1Porcentaje = 0.0;
float apps2Porcentaje = 0.0;


float diferenciaPorcentaje = 0.0;


// ================================================================
// VARIABLES DE FALLA
// ================================================================

bool fallaInstantanea = false;

bool fallaEnclavada = false;

bool temporizadorFallaActivo = false;

unsigned long tiempoInicioFalla = 0;


// ================================================================
// DETERMINAR SI UNA FALLA ES CORTOCIRCUITO
// ================================================================

/*
 * Determina si el tipo de falla recibido corresponde a un cortocircuito.
 * Se usa para decidir si debe activarse la salida PIN_INTERRUPCION.
 */
bool esCortocircuito(int falla) {

  if (
      falla == FALLA_APPS1_CORTO_GND ||
      falla == FALLA_APPS1_CORTO_VCC ||
      falla == FALLA_APPS2_CORTO_GND ||
      falla == FALLA_APPS2_CORTO_VCC
     ) {

    return true;

  }

  return false;

}


// ================================================================
// CONVERTIR ADC A VOLTAJE (ESP32)
// ================================================================
//
// ESP32: ADC de 12 bits (0-4095), rango 0-3.3V.
//
// Si usas un divisor resistivo para bajar la señal de 5V a 3.3V,
// ajusta la constante FACTOR_DIVISOR.
// Ejemplo: divisor 2:1 (5V -> 2.5V) => factor = 2.0
//

/*
 * Convierte la lectura cruda del ADC (0 a 4095) a voltaje.
 *
 * IMPORTANTE:
 * - El ADC del ESP32 trabaja hasta aproximadamente 3.3 V.
 * - Si APPS1 o APPS2 pueden entregar más de 3.3 V, la señal debe reducirse
 *   mediante un divisor resistivo o circuito de acondicionamiento.
 * - FACTOR_DIVISOR debe representar la relación entre el voltaje real del
 *   sensor y el voltaje que llega físicamente al pin ADC.
 */
float convertirADCaVoltaje(int adc) {

  // Voltaje real medido en el pin del ESP32
  float voltajePin = adc * (VOLTAJE_REF_ADC / RESOLUCION_ADC);

  // Si usas divisor, multiplica por el factor.
  // Si el sensor ya está acondicionado a 0-3.3V, factor = 1.0
  const float FACTOR_DIVISOR = 1.0;   // Cambia según tu divisor

  return voltajePin * FACTOR_DIVISOR;

}


// ================================================================
// NORMALIZAR APPS1
// ================================================================

/*
 * Convierte el voltaje de APPS1 a una posición equivalente de 0 a 100 %.
 * La relación utilizada es lineal entre APPS1_MIN_V y APPS1_MAX_V.
 * Cualquier resultado menor a 0 % o mayor a 100 % se limita al rango válido.
 */
float normalizarAPPS1(float voltaje) {

  float porcentaje =
    (
      (voltaje - APPS1_MIN_V) /
      (APPS1_MAX_V - APPS1_MIN_V)
    )
    * 100.0;


  if (porcentaje < 0.0) {

    porcentaje = 0.0;

  }


  if (porcentaje > 100.0) {

    porcentaje = 100.0;

  }


  return porcentaje;

}


// ================================================================
// NORMALIZAR APPS2
// ================================================================

/*
 * Convierte el voltaje de APPS2 a una posición equivalente de 0 a 100 %.
 * Esto permite comparar ambos sensores aunque tengan rangos de voltaje
 * diferentes.
 */
float normalizarAPPS2(float voltaje) {

  float porcentaje =
    (
      (voltaje - APPS2_MIN_V) /
      (APPS2_MAX_V - APPS2_MIN_V)
    )
    * 100.0;


  if (porcentaje < 0.0) {

    porcentaje = 0.0;

  }


  if (porcentaje > 100.0) {

    porcentaje = 100.0;

  }


  return porcentaje;

}


// ================================================================
// LEER SENSORES
// ================================================================

/*
 * Realiza todo el procesamiento de entrada:
 * 1. Lee los dos canales ADC.
 * 2. Convierte las lecturas a voltaje.
 * 3. Normaliza cada sensor a 0-100 %.
 * 4. Calcula la diferencia absoluta entre ambos porcentajes.
 */
void leerSensores() {


  // Leer ADC (ESP32: analogRead devuelve 0-4095)

  apps1ADC =
    analogRead(PIN_APPS1);

  apps2ADC =
    analogRead(PIN_APPS2);


  // Convertir ADC a voltaje real del sensor

  apps1Voltaje =
    convertirADCaVoltaje(
      apps1ADC
    );


  apps2Voltaje =
    convertirADCaVoltaje(
      apps2ADC
    );


  // Convertir voltaje a porcentaje

  apps1Porcentaje =
    normalizarAPPS1(
      apps1Voltaje
    );


  apps2Porcentaje =
    normalizarAPPS2(
      apps2Voltaje
    );


  // Calcular diferencia absoluta

  diferenciaPorcentaje =
    apps1Porcentaje -
    apps2Porcentaje;


  if (diferenciaPorcentaje < 0) {

    diferenciaPorcentaje =
      -diferenciaPorcentaje;

  }

}


// ================================================================
// DETECCION DE FALLAS
// ================================================================

/*
 * Evalúa las condiciones de falla en orden de prioridad.
 *
 * Prioridad:
 * 1. Cortocircuito a GND.
 * 2. Cortocircuito a VCC.
 * 3. Señal fuera del rango eléctrico permitido.
 * 4. Diferencia de plausibilidad mayor al 10 %.
 *
 * La función solo detecta la falla instantánea; la confirmación temporal
 * se realiza posteriormente en gestionarFalla().
 */
void detectarFalla() {


  fallaInstantanea = false;

  tipoFallaActual =
    FALLA_NINGUNA;


  // APPS1 CORTO A GND

  if (
      apps1Voltaje <=
      UMBRAL_CORTO_GND
     ) {

    fallaInstantanea = true;

    tipoFallaActual =
      FALLA_APPS1_CORTO_GND;

    return;

  }


  // APPS1 CORTO A VCC

  if (
      apps1Voltaje >=
      UMBRAL_CORTO_VCC
     ) {

    fallaInstantanea = true;

    tipoFallaActual =
      FALLA_APPS1_CORTO_VCC;

    return;

  }


  // APPS2 CORTO A GND

  if (
      apps2Voltaje <=
      UMBRAL_CORTO_GND
     ) {

    fallaInstantanea = true;

    tipoFallaActual =
      FALLA_APPS2_CORTO_GND;

    return;

  }


  // APPS2 CORTO A VCC

  if (
      apps2Voltaje >=
      UMBRAL_CORTO_VCC
     ) {

    fallaInstantanea = true;

    tipoFallaActual =
      FALLA_APPS2_CORTO_VCC;

    return;

  }


  // APPS1 FUERA DE RANGO

  if (
      apps1Voltaje <
      APPS1_LIM_INF
      ||
      apps1Voltaje >
      APPS1_LIM_SUP
     ) {

    fallaInstantanea = true;

    tipoFallaActual =
      FALLA_APPS1_FUERA_RANGO;

    return;

  }


  // APPS2 FUERA DE RANGO

  if (
      apps2Voltaje <
      APPS2_LIM_INF
      ||
      apps2Voltaje >
      APPS2_LIM_SUP
     ) {

    fallaInstantanea = true;

    tipoFallaActual =
      FALLA_APPS2_FUERA_RANGO;

    return;

  }


  // FALLA DE PLAUSIBILIDAD

  if (
      diferenciaPorcentaje >
      TOLERANCIA_PLAUSIBILIDAD
     ) {

    fallaInstantanea = true;

    tipoFallaActual =
      FALLA_PLAUSIBILIDAD;

    return;

  }

}


// ================================================================
// GESTIONAR FALLA
// ================================================================

/*
 * Implementa la persistencia temporal y el enclavamiento de la falla.
 *
 * - Una falla instantánea inicia un temporizador.
 * - Si desaparece antes de 100 ms, el sistema vuelve a ESTADO_OK.
 * - Si permanece durante 100 ms o más, queda confirmada y enclavada.
 * - Una falla enclavada no se elimina automáticamente aunque desaparezca
 *   la condición que la originó.
 */
void gestionarFalla() {


  if (fallaEnclavada) {

    estadoSistema =
      ESTADO_FALLA_CONFIRMADA;

    return;

  }


  if (fallaInstantanea) {


    if (!temporizadorFallaActivo) {


      temporizadorFallaActivo =
        true;


      tiempoInicioFalla =
        millis();


      estadoSistema =
        ESTADO_FALLA_PENDIENTE;

    }


    else {


      if (
          millis() -
          tiempoInicioFalla
          >=
          TIEMPO_CONFIRMACION_FALLA
         ) {


        fallaEnclavada =
          true;


        tipoFallaEnclavada =
          tipoFallaActual;


        estadoSistema =
          ESTADO_FALLA_CONFIRMADA;

      }

    }

  }


  else {


    temporizadorFallaActivo =
      false;


    tiempoInicioFalla =
      0;


    estadoSistema =
      ESTADO_OK;

  }

}


// ================================================================
// ACTUALIZAR SALIDAS
// ================================================================

/*
 * Actualiza las salidas físicas según el estado del sistema.
 *
 * ESTADO_OK o FALLA_PENDIENTE:
 * - LED verde encendido.
 * - LED rojo apagado.
 * - Motor habilitado.
 *
 * FALLA_CONFIRMADA:
 * - LED verde apagado.
 * - LED rojo encendido.
 * - Motor deshabilitado.
 *
 * La salida de interrupción se activa únicamente cuando la falla actual
 * o enclavada corresponde a un cortocircuito.
 */
void actualizarSalidas() {


  bool activarInterrupcion =
    false;


  if (
      esCortocircuito(
        (int)tipoFallaActual
      )
     ) {

    activarInterrupcion =
      true;

  }


  if (
      fallaEnclavada &&
      esCortocircuito(
        (int)tipoFallaEnclavada
      )
     ) {

    activarInterrupcion =
      true;

  }


  digitalWrite(
    PIN_INTERRUPCION,
    activarInterrupcion
      ? HIGH
      : LOW
  );


  if (
      estadoSistema ==
      ESTADO_OK
     ) {


    digitalWrite(
      PIN_LED_VERDE,
      HIGH
    );


    digitalWrite(
      PIN_LED_ROJO,
      LOW
    );


    digitalWrite(
      PIN_MOTOR_ENABLE,
      HIGH
    );

  }


  else if (
      estadoSistema ==
      ESTADO_FALLA_PENDIENTE
     ) {


    digitalWrite(
      PIN_LED_VERDE,
      HIGH
    );


    digitalWrite(
      PIN_LED_ROJO,
      LOW
    );


    digitalWrite(
      PIN_MOTOR_ENABLE,
      HIGH
    );

  }


  else {


    digitalWrite(
      PIN_LED_VERDE,
      LOW
    );


    digitalWrite(
      PIN_LED_ROJO,
      HIGH
    );


    digitalWrite(
      PIN_MOTOR_ENABLE,
      LOW
    );

  }

}


// ================================================================
// RESET DE FALLA
// ================================================================

/*
 * Permite eliminar manualmente una falla enclavada escribiendo RESET
 * en el Monitor Serial.
 *
 * Por seguridad, el reset solo se acepta cuando:
 * - Existe una falla enclavada.
 * - Ambos sensores están por debajo del 5 %.
 * - Ya no existe una falla instantánea.
 */
void procesarReset() {


  if (!Serial.available()) {

    return;

  }


  String comando =
    Serial.readStringUntil('\n');


  comando.trim();


  if (
      !comando.equalsIgnoreCase(
        "RESET"
      )
     ) {

    return;

  }


  if (
      fallaEnclavada
      &&
      apps1Porcentaje < 5.0
      &&
      apps2Porcentaje < 5.0
      &&
      !fallaInstantanea
     ) {


    fallaEnclavada =
      false;


    fallaInstantanea =
      false;


    temporizadorFallaActivo =
      false;


    tiempoInicioFalla =
      0;


    tipoFallaActual =
      FALLA_NINGUNA;


    tipoFallaEnclavada =
      FALLA_NINGUNA;


    estadoSistema =
      ESTADO_OK;


    Serial.println(
      "RESET OK - Sistema restablecido"
    );

  }


  else {


    Serial.println(
      "RESET FALLIDO - Lleva ambos APPS a reposo y elimina la falla"
    );

  }

}


// ================================================================
// MOSTRAR TIPO DE FALLA
// ================================================================

/*
 * Traduce el código interno de falla a texto legible para mostrarlo
 * en el Monitor Serial.
 */
void mostrarTipoFalla(int falla) {


  switch (falla) {


    case FALLA_NINGUNA:

      Serial.print(
        "NINGUNA"
      );

      break;


    case FALLA_PLAUSIBILIDAD:

      Serial.print(
        "PLAUSIBILIDAD"
      );

      break;


    case FALLA_APPS1_FUERA_RANGO:

      Serial.print(
        "APPS1 FUERA DE RANGO"
      );

      break;


    case FALLA_APPS2_FUERA_RANGO:

      Serial.print(
        "APPS2 FUERA DE RANGO"
      );

      break;


    case FALLA_APPS1_CORTO_GND:

      Serial.print(
        "APPS1 CORTO A GND"
      );

      break;


    case FALLA_APPS1_CORTO_VCC:

      Serial.print(
        "APPS1 CORTO A VCC"
      );

      break;


    case FALLA_APPS2_CORTO_GND:

      Serial.print(
        "APPS2 CORTO A GND"
      );

      break;


    case FALLA_APPS2_CORTO_VCC:

      Serial.print(
        "APPS2 CORTO A VCC"
      );

      break;

  }

}


// ================================================================
// TELEMETRIA
// ================================================================

/*
 * Envía al Monitor Serial el estado completo del sistema:
 * voltajes, porcentajes normalizados, diferencia entre sensores,
 * estado de la máquina de estados, tipo de falla, interrupción y motor.
 */
void mostrarTelemetria() {


  Serial.print(
    "APPS1: "
  );


  Serial.print(
    apps1Voltaje,
    3
  );


  Serial.print(
    " V | "
  );


  Serial.print(
    apps1Porcentaje,
    1
  );


  Serial.print(
    "%"
  );


  Serial.print(
    " || APPS2: "
  );


  Serial.print(
    apps2Voltaje,
    3
  );


  Serial.print(
    " V | "
  );


  Serial.print(
    apps2Porcentaje,
    1
  );


  Serial.print(
    "%"
  );


  Serial.print(
    " || DIF: "
  );


  Serial.print(
    diferenciaPorcentaje,
    1
  );


  Serial.print(
    "%"
  );


  Serial.print(
    " || ESTADO: "
  );


  if (
      estadoSistema ==
      ESTADO_OK
     ) {


    Serial.print(
      "OK"
    );

  }


  else if (
      estadoSistema ==
      ESTADO_FALLA_PENDIENTE
     ) {


    Serial.print(
      "FALLA PENDIENTE"
    );

  }


  else {


    Serial.print(
      "FALLA CONFIRMADA"
    );

  }


  Serial.print(
    " || FALLA: "
  );


  if (fallaEnclavada) {


    mostrarTipoFalla(
      (int)tipoFallaEnclavada
    );

  }


  else {


    mostrarTipoFalla(
      (int)tipoFallaActual
    );

  }


  Serial.print(
    " || INTERRUPCION: "
  );


  Serial.print(
    digitalRead(
      PIN_INTERRUPCION
    )
  );


  Serial.print(
    " || MOTOR: "
  );


  if (
      estadoSistema ==
      ESTADO_FALLA_CONFIRMADA
     ) {


    Serial.print(
      "OFF"
    );

  }


  else {


    Serial.print(
      "ON"
    );

  }


  Serial.println();

}


// ================================================================
// SETUP
// ================================================================

/*
 * Inicialización del sistema.
 * Configura entradas, salidas y comunicación serial.
 * El arranque comienza en un estado seguro con el motor deshabilitado
 * hasta realizar la primera lectura y evaluación de los sensores.
 */
void setup() {


  // Entradas analógicas

  pinMode(
    PIN_APPS1,
    INPUT
  );


  pinMode(
    PIN_APPS2,
    INPUT
  );


  // Salidas digitales

  pinMode(
    PIN_LED_ROJO,
    OUTPUT
  );


  pinMode(
    PIN_LED_VERDE,
    OUTPUT
  );


  pinMode(
    PIN_MOTOR_ENABLE,
    OUTPUT
  );


  pinMode(
    PIN_INTERRUPCION,
    OUTPUT
  );


  Serial.begin(
    115200
  );


  // ==============================================================
  // ESTADO SEGURO DE ARRANQUE
  // ==============================================================

  digitalWrite(
    PIN_LED_VERDE,
    LOW
  );


  digitalWrite(
    PIN_LED_ROJO,
    HIGH
  );


  digitalWrite(
    PIN_MOTOR_ENABLE,
    LOW
  );


  digitalWrite(
    PIN_INTERRUPCION,
    LOW
  );


  delay(200);


  // Primera lectura

  leerSensores();

  detectarFalla();

  gestionarFalla();

  actualizarSalidas();


  Serial.println(
    "========================================"
  );


  Serial.println(
    "Sistema APPS iniciado (ESP32)"
  );


  Serial.println(
    "APPS1: 0.415 - 4.585 V"
  );


  Serial.println(
    "APPS2: 1.251 - 3.749 V"
  );


  Serial.println(
    "Tolerancia plausibilidad: 10%"
  );


  Serial.println(
    "Persistencia de falla: 100 ms"
  );


  Serial.println(
    "========================================"
  );

}


// ================================================================
// LOOP
// ================================================================

/*
 * Ciclo principal.
 *
 * El orden es importante:
 * 1. Leer sensores.
 * 2. Detectar una posible falla.
 * 3. Gestionar temporización/enclavamiento.
 * 4. Actualizar las salidas.
 * 5. Revisar si el usuario solicitó RESET.
 * 6. Enviar telemetría cada 100 ms.
 */
void loop() {


  leerSensores();

  detectarFalla();

  gestionarFalla();

  actualizarSalidas();

  procesarReset();


  if (
      millis() -
      tiempoUltimoEnvio
      >=
      INTERVALO_ENVIO
     ) {


    mostrarTelemetria();


    tiempoUltimoEnvio =
      millis();

  }

}