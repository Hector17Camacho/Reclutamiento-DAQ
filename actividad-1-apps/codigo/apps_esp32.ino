#include <Arduino.h>

const uint8_t APPS1_PIN = 34;
const uint8_t APPS2_PIN = 35;
const uint8_t ALERT_LED_PIN = 25;
const uint8_t INTERRUPT_PIN = 26;
const uint8_t MOTOR_ENABLE_PIN = 27;

const unsigned long FAULT_CONFIRMATION_TIME_MS = 100;
const float MAX_ALLOWED_DIFFERENCE_PCT = 10.0f;

const int APPS1_ADC_MIN = 500;
const int APPS1_ADC_MAX = 3500;
const int APPS2_ADC_MIN = 700;
const int APPS2_ADC_MAX = 3300;

const float ADC_REFERENCE_VOLTAGE = 3.3f;
const float ADC_MAX_COUNTS = 4095.0f;
const unsigned long SERIAL_PRINT_INTERVAL_MS = 100;

struct SensorData {
  int adc = 0;
  float voltage = 0.0f;
  float percentage = 0.0f;
};

SensorData apps1;
SensorData apps2;

bool faultDetected = false;
bool motorEnabled = true;
bool interruptActive = false;
bool faultConditionActive = false;
unsigned long faultStartTime = 0;
unsigned long faultActiveTimeMs = 0;
unsigned long lastPrintTime = 0;
float channelDifferencePct = 0.0f;
float requestedAccelerationPct = 0.0f;

void readSensors();
float convertToPercentage(int adcValue, int adcMin, int adcMax);
bool checkPlausibility(float apps1Pct, float apps2Pct, float &differencePct);
void updateFaultTimer(bool plausibleState);
void enableMotor();
void disableMotor();
void updateIndicators();
void printSerialData();

void setup() {
  Serial.begin(115200);

  pinMode(ALERT_LED_PIN, OUTPUT);
  pinMode(INTERRUPT_PIN, OUTPUT);
  pinMode(MOTOR_ENABLE_PIN, OUTPUT);

  digitalWrite(ALERT_LED_PIN, LOW);
  digitalWrite(INTERRUPT_PIN, LOW);
  digitalWrite(MOTOR_ENABLE_PIN, HIGH);
}

void loop() {
  readSensors();

  const bool isPlausible = checkPlausibility(apps1.percentage, apps2.percentage, channelDifferencePct);
  updateFaultTimer(isPlausible);

  // ==============================
  // CONTROL DE SEGURIDAD DEL MOTOR
  // ==============================
  if (faultDetected) {
    requestedAccelerationPct = 0.0f;
    disableMotor();
  } else {
    requestedAccelerationPct = (apps1.percentage + apps2.percentage) * 0.5f;
    enableMotor();
  }

  updateIndicators();
  printSerialData();
}

void readSensors() {
  apps1.adc = analogRead(APPS1_PIN);
  apps2.adc = analogRead(APPS2_PIN);

  apps1.voltage = (static_cast<float>(apps1.adc) / ADC_MAX_COUNTS) * ADC_REFERENCE_VOLTAGE;
  apps2.voltage = (static_cast<float>(apps2.adc) / ADC_MAX_COUNTS) * ADC_REFERENCE_VOLTAGE;

  apps1.percentage = convertToPercentage(apps1.adc, APPS1_ADC_MIN, APPS1_ADC_MAX);
  apps2.percentage = convertToPercentage(apps2.adc, APPS2_ADC_MIN, APPS2_ADC_MAX);
}

float convertToPercentage(int adcValue, int adcMin, int adcMax) {
  const int boundedAdc = constrain(adcValue, adcMin, adcMax);
  const float range = static_cast<float>(adcMax - adcMin);

  if (range <= 0.0f) {
    return 0.0f;
  }

  return ((static_cast<float>(boundedAdc - adcMin)) / range) * 100.0f;
}

bool checkPlausibility(float apps1Pct, float apps2Pct, float &differencePct) {
  differencePct = fabsf(apps1Pct - apps2Pct);
  return differencePct <= MAX_ALLOWED_DIFFERENCE_PCT;
}

void updateFaultTimer(bool plausibleState) {
  const unsigned long currentTime = millis();

  if (!plausibleState) {
    if (!faultConditionActive) {
      faultConditionActive = true;
      faultStartTime = currentTime;
    }

    faultActiveTimeMs = currentTime - faultStartTime;
    faultDetected = faultActiveTimeMs >= FAULT_CONFIRMATION_TIME_MS;
  } else {
    faultConditionActive = false;
    faultDetected = false;
    faultActiveTimeMs = 0;
    faultStartTime = 0;
  }
}

void enableMotor() {
  motorEnabled = true;
}

void disableMotor() {
  motorEnabled = false;
}

void updateIndicators() {
  interruptActive = faultDetected;

  digitalWrite(ALERT_LED_PIN, faultDetected ? HIGH : LOW);
  digitalWrite(INTERRUPT_PIN, interruptActive ? HIGH : LOW);
  digitalWrite(MOTOR_ENABLE_PIN, motorEnabled ? HIGH : LOW);
}

void printSerialData() {
  const unsigned long now = millis();
  if (now - lastPrintTime < SERIAL_PRINT_INTERVAL_MS) {
    return;
  }
  lastPrintTime = now;

  const char *plausibilityText = faultDetected ? "FALLA CONFIRMADA" : "PLAUSIBLE";
  const char *motorText = motorEnabled ? "HABILITADO" : "DESHABILITADO";
  const char *interruptText = interruptActive ? "ACTIVA" : "INACTIVA";

  Serial.println("----------------------------------------");

  Serial.print("ADC APPS1: ");
  Serial.println(apps1.adc);
  Serial.print("Voltaje APPS1: ");
  Serial.print(apps1.voltage, 3);
  Serial.println(" V");
  Serial.print("APPS1: ");
  Serial.print(apps1.percentage, 2);
  Serial.println(" %");

  Serial.print("ADC APPS2: ");
  Serial.println(apps2.adc);
  Serial.print("Voltaje APPS2: ");
  Serial.print(apps2.voltage, 3);
  Serial.println(" V");
  Serial.print("APPS2: ");
  Serial.print(apps2.percentage, 2);
  Serial.println(" %");

  Serial.print("Diferencia: ");
  Serial.print(channelDifferencePct, 2);
  Serial.println(" %");

  Serial.print("Tiempo falla activa: ");
  Serial.print(faultActiveTimeMs);
  Serial.println(" ms");

  Serial.print("Estado: ");
  Serial.println(plausibilityText);

  Serial.print("Motor: ");
  Serial.println(motorText);

  Serial.print("Interrupción: ");
  Serial.println(interruptText);

  Serial.print("Aceleración solicitada: ");
  Serial.print(requestedAccelerationPct, 2);
  Serial.println(" %");
}
