
"""
APPS PLAUSIBILITY MONITOR — FORMULA SAE
Dashboard de adquisición de datos para visualización en tiempo real del sistema APPS redundante.
"""
import sys
import time
import math
import threading
import traceback
import re  
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QTabWidget, QTabBar, QComboBox, QPushButton,
    QTextEdit, QLineEdit, QSlider, QProgressBar, QSizePolicy,
    QSplitter, QMessageBox, QFileDialog
)
from PyQt5.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPixmap, QLinearGradient,
    QRadialGradient, QPainterPath, QTransform
)
from PyQt5.QtCore import Qt, QTimer, QPointF, QRectF, pyqtSignal

import serial
import serial.tools.list_ports

# ─────────────────────────────────────────────────────────────────
#  PALETAS DE COLORES
# ─────────────────────────────────────────────────────────────────

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

LIGHT_PALETTE = {
    "bg0":     "#F2F5F9",
    "bg1":     "#FFFFFF",
    "bg2":     "#E9EDF2",
    "bg3":     "#DCE2EC",
    "cyan":    "#1E40AF",
    "blue":    "#3730A3",
    "gold":    "#B45309",
    "red":     "#991B1B",
    "green":   "#14532D",
    "text_w":  "#111827",
    "text_g":  "#4B5563",
    "border":  "#1E3A8A",
    "critical": "#DC2626"
}

CURRENT_THEME = "dark"
CURRENT_PALETTE = DARK_PALETTE

def C(key):
    """Devuelve color seguro desde la paleta actual."""
    return CURRENT_PALETTE.get(key, CURRENT_PALETTE.get("cyan", "#00E5FF"))

# ─────────────────────────────────────────────────────────────────
#  FUENTES
# ─────────────────────────────────────────────────────────────────
FONT_DARK = "Segoe UI, Roboto, sans-serif"
FONT_LIGHT = "Inter, 'Segoe UI', Roboto, sans-serif"
FONT = FONT_DARK

# ─────────────────────────────────────────────────────────────────
#  CONSTANTES DE APPS
# ─────────────────────────────────────────────────────────────────
MAX_DIFFERENCE_PERCENT = 10.0        # % máximo permitido antes de fallo
GAUGE_GREEN_MAX = 20
GAUGE_CYAN_MAX = 60
GAUGE_GOLD_MAX = 85
# (85-100 -> naranja/rojo)

def gauge_color(percent):
    """Color dinámico según posición del pedal (0-100%)."""
    if percent <= GAUGE_GREEN_MAX:
        return C("green")
    elif percent <= GAUGE_CYAN_MAX:
        return C("cyan")
    elif percent <= GAUGE_GOLD_MAX:
        return C("gold")
    else:
        return C("red")

# ─────────────────────────────────────────────────────────────────
#  HELPERS DE ESTILO
# ─────────────────────────────────────────────────────────────────
def card_style(border=None):
    b = border or C("border")
    return f"""
        QFrame{{
            background:{C('bg1')};
            border-radius:12px;
            border:1px solid {b};
        }}
    """

def lbl(color, size=11, bold=False):
    w = "bold" if bold else "normal"
    return f"color:{color};font-family:{FONT};font-size:{size}px;font-weight:{w};"

def btn_style(fg, border):
    return f"""
        QPushButton{{
            background:{C('bg2')};
            color:{fg};
            border:1.5px solid {border};
            border-radius:8px;
            padding:7px 18px;
            font-family:{FONT};
            font-weight:bold;
            font-size:12px;
        }}
        QPushButton:hover{{
            background:{C('bg3')};
            border:1.5px solid {C('cyan')};
        }}
        QPushButton:pressed{{
            background:{border};
            color:{C('bg1')};
        }}
        QPushButton:disabled{{
            background:{C('bg2')};
            color:{C('text_g')};
            border:1.5px solid {C('border')};
        }}
    """

# ─────────────────────────────────────────────────────────────────
#  WIDGETS PERSONALIZADOS
# ─────────────────────────────────────────────────────────────────

class DualLineGraph(QWidget):
    """
    Gráfica temporal que muestra APPS1 y APPS2 normalizados (%).
    """
    def __init__(self, color_key1="green", color_key2="cyan", max_pts=150, parent=None):
        super().__init__(parent)
        self.data1 = []
        self.data2 = []
        self.max_pts = max_pts
        self.color_key1 = color_key1
        self.color_key2 = color_key2
        self.setMinimumHeight(80)

    def push(self, v1, v2):
        try:
            v1 = float(v1)
            v2 = float(v2)
        except:
            return
        self.data1.append(v1)
        self.data2.append(v2)
        if len(self.data1) > self.max_pts:
            self.data1.pop(0)
        if len(self.data2) > self.max_pts:
            self.data2.pop(0)
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(C("bg2")))
        # rejilla
        p.setPen(QPen(QColor(C("border")), 1, Qt.DashLine))
        for i in range(1, 5):
            y = int(h * i / 4)
            p.drawLine(0, y, w, y)
        # etiquetas Y
        p.setFont(QFont(FONT, 8))
        p.setPen(QColor(C("text_g")))
        for i in range(5):
            p.drawText(2, int(h * i / 4)-8, 40, 16, Qt.AlignLeft, f"{100-i*25}%")
        # dibujar líneas
        def draw_line(data, color_key):
            if len(data) < 2:
                return
            pts = [QPointF(int(i/(len(data)-1)*(w-4))+2,
                           int((1 - v/100.0) * (h-10)) + 5)
                   for i, v in enumerate(data)]
            pen = QPen(QColor(C(color_key)), 2, Qt.SolidLine, Qt.RoundCap)
            p.setPen(pen)
            for i in range(len(pts)-1):
                p.drawLine(pts[i], pts[i+1])

        draw_line(self.data1, self.color_key1)
        draw_line(self.data2, self.color_key2)

        # leyenda
        p.setFont(QFont(FONT, 9, QFont.Bold))
        p.setPen(QColor(C("text_w")))
        p.drawText(w-150, 5, 145, 16, Qt.AlignRight, f"APPS1 ({C(self.color_key1)})  APPS2 ({C(self.color_key2)})")

        # bordes
        p.setPen(QPen(QColor(C("border")), 1))
        p.drawRect(0, 0, w-1, h-1)
        p.end()

    def refresh_style(self):
        self.update()


class PedalGauge(QWidget):
    """
    Velocímetro circular para mostrar posición del pedal 0-100%.
    Incluye escala, aguja, arco de progreso, valor numérico, RAW y voltaje.
    """
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.title = title
        self.value = 0.0
        self.raw = 0
        self.voltage = 0.0
        self._blink = False
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._flip_blink)
        self._fault_border = False
        self.setMinimumSize(220, 280)

    def set_value(self, pct, raw, voltage):
        self.value = max(0.0, min(100.0, float(pct)))
        self.raw = int(raw)
        self.voltage = float(voltage)
        self.update()

    def set_fault_border(self, active):
        self._fault_border = active
        if active and not self._blink_timer.isActive():
            self._blink_timer.start(400)
        elif not active and self._blink_timer.isActive():
            self._blink_timer.stop()
            self._blink = False
        self.update()

    def _flip_blink(self):
        self._blink = not self._blink
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w/2, h/2 - 15
        R = min(w, h-40) * 0.4

        # Color dinámico según valor
        col = QColor(gauge_color(self.value))
        border_pen = QPen(col, 2.5)
        if self._fault_border and self._blink:
            border_pen = QPen(QColor(C("critical")), 3)

        # Fondo
        gr = QRadialGradient(cx, cy, R)
        gr.setColorAt(0, QColor(C("bg1")))
        gr.setColorAt(1, QColor(C("bg2")))
        p.setBrush(QBrush(gr))
        p.setPen(border_pen)
        p.drawEllipse(QPointF(cx, cy), R, R)

        ar = QRectF(cx-R+12, cy-R+12, (R-12)*2, (R-12)*2)

        # Arco de fondo
        p.setPen(QPen(QColor(C("border")), 14, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(ar, 210*16, -240*16)

        # Zonas de color
        def zone(sv, ev, zc):
            sp = int((210 - sv/100.0*240)*16)
            span = int(-(ev-sv)/100.0*240*16)
            p.setPen(QPen(QColor(C(zc)), 5, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(ar, sp, span)
        zone(0, GAUGE_GREEN_MAX, "green")
        zone(GAUGE_GREEN_MAX, GAUGE_CYAN_MAX, "cyan")
        zone(GAUGE_CYAN_MAX, GAUGE_GOLD_MAX, "gold")
        zone(GAUGE_GOLD_MAX, 100, "red")

        # Arco de progreso
        span = int(-240 * (self.value / 100.0) * 16)
        p.setPen(QPen(col, 14, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(ar, 210*16, span)

        # Marcas
        p.setPen(QPen(QColor(C("text_g")), 1.5))
        p.setFont(QFont(FONT, 7))
        for i in range(9):
            a_deg = 210 - i * (240/8)
            a = math.radians(a_deg)
            p.drawLine(QPointF(cx+(R-20)*math.cos(a), cy-(R-20)*math.sin(a)),
                       QPointF(cx+(R-8)*math.cos(a), cy-(R-8)*math.sin(a)))
            val = int(i * 100 / 8)
            p.drawText(int(cx+(R-34)*math.cos(a)-12), int(cy-(R-34)*math.sin(a)-7),
                       24, 14, Qt.AlignCenter, str(val))

        # Aguja
        a = math.radians(210 - (self.value/100.0)*240)
        p.setPen(QPen(col, 3, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx, cy), QPointF(cx+(R-28)*math.cos(a), cy-(R-28)*math.sin(a)))
        p.setBrush(QBrush(col))
        p.setPen(QPen(QColor(C("bg0")), 2))
        p.drawEllipse(QPointF(cx, cy), 7, 7)

        # Valor numérico
        p.setFont(QFont(FONT, 16, QFont.Bold))
        p.setPen(col)
        p.drawText(QRectF(cx-60, cy+15, 120, 30), Qt.AlignCenter, f"{self.value:.1f}%")

        # Título
        p.setFont(QFont(FONT, 11, QFont.Bold))
        p.setPen(QColor(C("text_w")))
        p.drawText(QRectF(cx-60, cy+R+10, 120, 20), Qt.AlignCenter, self.title)

        # RAW y voltaje
        p.setFont(QFont(FONT, 9))
        p.setPen(QColor(C("text_g")))
        p.drawText(QRectF(cx-60, cy+R+30, 120, 18), Qt.AlignCenter, f"Raw: {self.raw}")
        p.drawText(QRectF(cx-60, cy+R+48, 120, 18), Qt.AlignCenter, f"Voltaje: {self.voltage:.2f} V")
        p.end()


class PlausibilityBar(QWidget):
    """Barra horizontal que muestra la diferencia APPS1-APPS2."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.diff = 0.0
        self.setMinimumHeight(30)
        self.setMaximumHeight(50)

    def set_difference(self, val):
        self.diff = float(val)
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(C("bg2")))
        # fondo barra
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(C("bg3")))
        bar_h = 14
        bar_y = (h - bar_h) / 2
        p.drawRoundedRect(10, int(bar_y), w-20, bar_h, 4, 4)

        # barra de progreso de la diferencia
        diff_clamped = min(self.diff, MAX_DIFFERENCE_PERCENT * 1.5)
        pct = diff_clamped / (MAX_DIFFERENCE_PERCENT * 1.5)
        fill_w = int((w-20) * pct)
        if self.diff <= 3.0:
            color = C("green")
        elif self.diff <= MAX_DIFFERENCE_PERCENT:
            color = C("gold")
        else:
            color = C("red")
        p.setBrush(QColor(color))
        p.drawRoundedRect(10, int(bar_y), fill_w, bar_h, 4, 4)

        # texto
        p.setPen(QColor(C("text_w")))
        p.setFont(QFont(FONT, 10, QFont.Bold))
        p.drawText(QRectF(0, 0, w, h-4), Qt.AlignCenter, f"Diferencia: {self.diff:.1f} %")
        p.end()


class StatusIndicator(QLabel):
    """Indicador tipo '●' con texto."""
    def __init__(self, label="", color_key="green", parent=None):
        super().__init__(parent)
        self.label = label
        self.color_key = color_key
        self.setup_ui()

    def setup_ui(self):
        self.setText(f"● {self.label}")
        self.setStyleSheet(lbl(C(self.color_key), 11, True))

    def set_state(self, label, color_key):
        self.label = label
        self.color_key = color_key
        self.setText(f"● {self.label}")
        self.setStyleSheet(lbl(C(self.color_key), 11, True))


# ─────────────────────────────────────────────────────────────────
#  PANELES COMPUESTOS
# ─────────────────────────────────────────────────────────────────

class APPSStatusPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(card_style())
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)

        title = QLabel("SYSTEM STATUS")
        title.setStyleSheet(lbl(C("cyan"), 13, True))
        lay.addWidget(title)

        self.status_ind = StatusIndicator("SYSTEM OK", "green")
        self.plausibility_ind = StatusIndicator("APPS PLAUSIBLE", "green")
        self.motor_ind = StatusIndicator("MOTOR ENABLED", "green")
        self.interrupt_ind = StatusIndicator("INTERRUPTION OFF", "green")

        lay.addWidget(self.status_ind)
        lay.addWidget(self.plausibility_ind)
        lay.addWidget(self.motor_ind)
        lay.addWidget(self.interrupt_ind)

        # Tipo de falla (oculto inicialmente)
        self.fault_type_label = QLabel("")
        self.fault_type_label.setStyleSheet(lbl(C("red"), 11, True))
        self.fault_type_label.setVisible(False)
        lay.addWidget(self.fault_type_label)

    def update_status(self, state, interrupt, motor, fault_type):
        """
        Actualiza los indicadores según el estado recibido.
        state: "OK", "FAULT_PENDING", "FAULT_LATCHED"
        interrupt: 0/1
        motor: 0/1 (1=habilitado)
        fault_type: string (NONE, PLAUSIBILITY_ERROR, etc.)
        """
        if state == "FAULT_LATCHED":
            self.status_ind.set_state("CRITICAL — APPS FAILURE", "red")
            self.plausibility_ind.set_state("APPS PLAUSIBILITY FAULT", "red")
            self.motor_ind.set_state("MOTOR DISABLED" if motor == 0 else "MOTOR ENABLED",
                                     "red" if motor == 0 else "green")
            self.interrupt_ind.set_state("INTERRUPTION ACTIVE" if interrupt == 1 else "INTERRUPTION OFF",
                                         "red" if interrupt == 1 else "green")
            self.fault_type_label.setVisible(True)
            self.fault_type_label.setText(f"FAULT TYPE: {fault_type.replace('_', ' ')}")
        elif state == "FAULT_PENDING":
            self.status_ind.set_state("CHECKING APPS PLAUSIBILITY", "gold")
            self.plausibility_ind.set_state("TEMPORARY MISMATCH", "gold")
            self.motor_ind.set_state("MOTOR ENABLED", "green")
            self.interrupt_ind.set_state("INTERRUPTION OFF", "green")
            self.fault_type_label.setVisible(False)
        else:  # OK
            self.status_ind.set_state("SYSTEM OK", "green")
            self.plausibility_ind.set_state("APPS PLAUSIBLE", "green")
            self.motor_ind.set_state("MOTOR ENABLED", "green")
            self.interrupt_ind.set_state("INTERRUPTION OFF", "green")
            self.fault_type_label.setVisible(False)

    def refresh_style(self):
        self.setStyleSheet(card_style())
        self.status_ind.setup_ui()
        self.plausibility_ind.setup_ui()
        self.motor_ind.setup_ui()
        self.interrupt_ind.setup_ui()
        self.fault_type_label.setStyleSheet(lbl(C("red"), 11, True))


# ─────────────────────────────────────────────────────────────────
#  GESTOR DE SIMULACIÓN
# ─────────────────────────────────────────────────────────────────
class SimulationManager:
    def __init__(self, dashboard):
        self.dashboard = dashboard
        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        self.active = False
        self.time = 0.0
        self.apps1 = 0.0
        self.apps2 = 0.0
        self.state = "OK"
        self.interrupt = 0
        self.motor = 1
        self.fault_type = "NONE"
        self._pending_count = 0
        self._manual_override = False

    def start(self):
        self.active = True
        self.timer.start(100)  # 10 Hz

    def stop(self):
        self.active = False
        self.timer.stop()

    def reset(self):
        self.time = 0.0
        self.apps1 = 0.0
        self.apps2 = 0.0
        self.state = "OK"
        self.interrupt = 0
        self.motor = 1
        self.fault_type = "NONE"
        self._pending_count = 0
        self._manual_override = False

    def _send_line(self):
        # Construir línea de telemetría
        apps1_raw = int(self.apps1 * 8.19)   # simulación arbitraria
        apps2_raw = int(self.apps2 * 8.19)
        apps1_v = self.apps1 * 5.0 / 100.0
        apps2_v = self.apps2 * 5.0 / 100.0
        diff = abs(self.apps1 - self.apps2)
        line = (f"apps1_raw:{apps1_raw},apps2_raw:{apps2_raw},"
                f"apps1_v:{apps1_v:.2f},apps2_v:{apps2_v:.2f},"
                f"apps1_pct:{self.apps1:.1f},apps2_pct:{self.apps2:.1f},"
                f"diff:{diff:.1f},state:{self.state},interrupt:{self.interrupt},"
                f"motor:{self.motor},fault:{self.fault_type}")
        self.dashboard.on_serial_data(line)

    def _tick(self):
        if not self.active or self._manual_override:
            return
        self.time += 0.1
        # Secuencia automática de demostración
        phase = (self.time % 40) / 40.0  # ciclo de 40 s
        if phase < 0.25:
            # aceleración 0 -> 100
            t = phase / 0.25
            self.apps1 = 100 * t
            self.apps2 = self.apps1 - 0.5  # pequeña diferencia
            self.state = "OK"
            self.interrupt = 0
            self.motor = 1
            self.fault_type = "NONE"
            self._pending_count = 0
        elif phase < 0.45:
            # retorno 100 -> 0
            t = (phase - 0.25) / 0.2
            self.apps1 = 100 * (1 - t)
            self.apps2 = self.apps1 - 0.5
            self.state = "OK"
        elif phase < 0.50:
            # discrepancia momentánea < 100 ms
            self.apps1 = 50.0
            self.apps2 = 30.0
            self.state = "FAULT_PENDING"
            self._pending_count += 1
            if self._pending_count >= 2:  # 200 ms
                # mantiene FAULT_PENDING pero no latch
                pass
        elif phase < 0.55:
            # vuelve a normal
            self.apps1 = 50.0
            self.apps2 = 49.5
            self.state = "OK"
            self._pending_count = 0
        elif phase < 0.65:
            # discrepancia sostenida
            self.apps1 = 75.0
            self.apps2 = 30.0
            self.state = "FAULT_PENDING"
            self._pending_count += 1
            if self._pending_count >= 1.5 * 10:  # 1500 ms -> latch
                self.state = "FAULT_LATCHED"
                self.interrupt = 1
                self.motor = 0
                self.fault_type = "PLAUSIBILITY_ERROR"
        else:
            # reset ciclo
            self.apps1 = 0
            self.apps2 = 0
            self.state = "OK"
            self.interrupt = 0
            self.motor = 1
            self.fault_type = "NONE"
            self._pending_count = 0
            self.time = 0.0

        self._send_line()

    def manual_normal(self):
        self._manual_override = True
        self.apps1 = 50.0
        self.apps2 = 49.8
        self.state = "OK"
        self.interrupt = 0
        self.motor = 1
        self.fault_type = "NONE"
        self._send_line()

    def manual_temp_fault(self):
        self._manual_override = True
        self.apps1 = 60.0
        self.apps2 = 40.0
        self.state = "FAULT_PENDING"
        self.interrupt = 0
        self.motor = 1
        self.fault_type = "NONE"
        self._send_line()

    def manual_plausibility_fault(self):
        self._manual_override = True
        self.apps1 = 70.0
        self.apps2 = 20.0
        self.state = "FAULT_LATCHED"
        self.interrupt = 1
        self.motor = 0
        self.fault_type = "PLAUSIBILITY_ERROR"
        self._send_line()

    def manual_apps1_short(self):
        self._manual_override = True
        self.apps1 = 0.0
        self.apps2 = 50.0
        self.state = "FAULT_LATCHED"
        self.interrupt = 1
        self.motor = 0
        self.fault_type = "APPS1_OUT_OF_RANGE"
        self._send_line()

    def manual_apps2_short(self):
        self._manual_override = True
        self.apps1 = 50.0
        self.apps2 = 0.0
        self.state = "FAULT_LATCHED"
        self.interrupt = 1
        self.motor = 0
        self.fault_type = "APPS2_OUT_OF_RANGE"
        self._send_line()

    def manual_reset(self):
        self._manual_override = False
        self.reset()
        self._send_line()


# ─────────────────────────────────────────────────────────────────
#  GESTOR SERIAL
# ─────────────────────────────────────────────────────────────────
class SerialManager:
    def __init__(self, dashboard):
        self.dashboard = dashboard
        self.port = None
        self.thread = None
        self.running = False
        self.baudrate = 115200

    def available_ports(self):
        return [p.device for p in serial.tools.list_ports.comports()]

    def connect(self, port):
        self.disconnect()
        try:
            self.port = serial.Serial(port=port, baudrate=self.baudrate, timeout=1)
            self.running = True
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()
            self.dashboard.log(f"✔ Conectado a {port} @ {self.baudrate} baud")
            return True
        except Exception as e:
            self.dashboard.log(f"✖ Error de conexión: {e}")
            return False

    def disconnect(self):
        if self.port and self.port.is_open:
            self.running = False
            if self.thread and self.thread.is_alive():
                self.thread.join(2)
            self.port.close()
            self.dashboard.log("⏻ Desconectado")
            return True
        return False

    def _loop(self):
        buffer = ""
        while self.running and self.port and self.port.is_open:
            try:
                if self.port.in_waiting > 0:
                    raw = self.port.read(self.port.in_waiting).decode('utf-8', errors='ignore')
                    buffer += raw
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        line = line.strip()
                        if line:
                            self.dashboard.on_serial_data(line)
                else:
                    time.sleep(0.01)
            except Exception as e:
                self.dashboard.log(f"⚠ Error bucle serial: {e}")
                time.sleep(0.1)


# ─────────────────────────────────────────────────────────────────
#  VENTANA PRINCIPAL
# ─────────────────────────────────────────────────────────────────
class APPSDashboard(QMainWindow):
    data_received = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("APPS PLAUSIBILITY MONITOR  |  FORMULA SAE")
        self.resize(1600, 900)
        self.msg_count = 0
        self.serial_mgr = SerialManager(self)
        self.sim_mgr = SimulationManager(self)
        self.data_received.connect(self._dispatch)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        root.addWidget(self._build_header())
        root.addWidget(self._build_tabs(), 1)
        self._refresh_ports()
        self.set_theme("dark")

    # ---------------- Tema y estilo ----------------
    def set_theme(self, theme):
        global CURRENT_THEME, CURRENT_PALETTE, FONT
        if theme not in ("dark", "light") or theme == CURRENT_THEME:
            return
        CURRENT_THEME = theme
        if theme == "dark":
            CURRENT_PALETTE = DARK_PALETTE
            FONT = FONT_DARK
            self.setWindowTitle("APPS PLAUSIBILITY MONITOR  |  FORMULA SAE  [DARK RACING]")
            self.theme_btn.setText("☀")
        else:
            CURRENT_PALETTE = LIGHT_PALETTE
            FONT = FONT_LIGHT
            self.setWindowTitle("APPS PLAUSIBILITY MONITOR  |  FORMULA SAE  [LIGHT TECHNICAL]")
            self.theme_btn.setText("🌙")
        QApplication.setFont(QFont(FONT.split(',')[0].strip(), 10))
        self._apply_global_style()
        self._refresh_all_styles()
        self.log(f"🎨 Tema cambiado a {theme.upper()}")

    def _apply_global_style(self):
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: {C('bg0')};
                color: {C('text_w')};
                font-family: {FONT};
            }}
            QScrollBar:vertical {{
                background: {C('bg2')}; width: 8px; border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {C('border')}; border-radius: 4px; min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {C('cyan')};
            }}
            QScrollBar:horizontal {{
                background: {C('bg2')}; height: 8px;
            }}
            QScrollBar::handle:horizontal {{
                background: {C('border')}; border-radius: 4px;
            }}
            QToolTip {{
                background: {C('bg1')}; color: {C('cyan')};
                border: 1px solid {C('cyan')}; font-size: 11px;
                font-family: {FONT};
            }}
            QMessageBox {{
                background-color: {C('bg1')};
                color: {C('text_w')};
            }}
            QMessageBox QLabel {{
                color: {C('text_w')};
            }}
            QMessageBox QPushButton {{
                background-color: {C('bg2')};
                color: {C('text_w')};
                border: 1px solid {C('border')};
                border-radius: 6px;
                padding: 5px 10px;
                font-family: {FONT};
            }}
            QMessageBox QPushButton:hover {{
                background-color: {C('bg3')};
                border-color: {C('cyan')};
            }}
            QSplitter::handle {{
                background: {C('border')};
            }}
        """)

    def _refresh_all_styles(self):
        """Actualiza estilos de todos los widgets personalizados."""
        self.status_chip.setStyleSheet(self._status_chip_style())
        self.port_combo.setStyleSheet(self._combo_style())
        self.conn_btn.setStyleSheet(self._conn_btn_style())
        self.sim_btn.setStyleSheet(self._sim_btn_style())
        self.theme_btn.setStyleSheet(self._theme_btn_style())
        self.tabs.setStyleSheet(self._tabs_style())
        self.gauge1.update()
        self.gauge2.update()
        self.graph.refresh_style()
        self.status_panel.refresh_style()
        self.plaus_bar.update()
        self.console.setStyleSheet(self._console_style())
        self.cmd_input.setStyleSheet(self._cmd_input_style())
        self.msg_count_lbl.setStyleSheet(lbl(C("text_g"), 10))
        for btn in self.sim_test_btns:
            btn.setStyleSheet(btn_style(C("text_w"), C("border")))

    # ---------- Componentes de la interfaz ----------
    def _build_header(self):
        hdr = QFrame()
        hdr.setFixedHeight(68)
        hdr.setStyleSheet(f"QFrame{{background:{C('bg1')};border-radius:12px;border:1px solid {C('border')};}}")
        lay = QHBoxLayout(hdr)
        lay.setContentsMargins(18, 0, 18, 0)
        lay.setSpacing(18)

        logo = QLabel("⬢")
        logo.setFixedSize(46, 46)
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet(f"QLabel{{font-size:24px;color:{C('cyan')};border:1.5px solid {C('cyan')};border-radius:8px;background:{C('bg2')};}}")

        tc = QVBoxLayout()
        tc.setSpacing(2)
        tc.addWidget(QLabel("APPS PLAUSIBILITY MONITOR", styleSheet=f"color:{C('cyan')};font-size:17px;font-weight:bold;letter-spacing:2px;"))
        tc.addWidget(QLabel("FORMULA SAE  ·  DATA ACQUISITION", styleSheet=f"color:{C('text_g')};font-size:9px;letter-spacing:2px;"))

        lay.addWidget(logo)
        lay.addLayout(tc)
        lay.addStretch()

        self.status_chip = QLabel("● DESCONECTADO")
        self.status_chip.setStyleSheet(self._status_chip_style())

        self.port_combo = QComboBox()
        self.port_combo.setFixedWidth(130)
        self.port_combo.setStyleSheet(self._combo_style())
        baud_combo = QComboBox()
        baud_combo.addItems(["9600", "19200", "38400", "57600", "115200"])
        baud_combo.setCurrentText("115200")
        baud_combo.setFixedWidth(90)
        baud_combo.setStyleSheet(self._combo_style())
        baud_combo.currentTextChanged.connect(lambda v: setattr(self.serial_mgr, 'baudrate', int(v)))

        self.conn_btn = QPushButton("CONECTAR")
        self.conn_btn.setCheckable(True)
        self.conn_btn.setFixedWidth(110)
        self.conn_btn.setStyleSheet(self._conn_btn_style())
        self.conn_btn.toggled.connect(self._toggle_connection)

        ref_btn = QPushButton("↻")
        ref_btn.setFixedSize(32, 32)
        ref_btn.setToolTip("Actualizar puertos")
        ref_btn.setStyleSheet(f"QPushButton{{background:{C('bg2')};color:{C('text_g')};border:1px solid {C('border')};border-radius:8px;font-size:14px;}}QPushButton:hover{{color:{C('cyan')};border:1px solid {C('cyan')};}}")
        ref_btn.clicked.connect(self._refresh_ports)

        self.sim_btn = QPushButton("SIM OFF")
        self.sim_btn.setCheckable(True)
        self.sim_btn.setFixedWidth(90)
        self.sim_btn.setStyleSheet(self._sim_btn_style())
        self.sim_btn.toggled.connect(self._toggle_sim)

        self.theme_btn = QPushButton("☀")
        self.theme_btn.setFixedWidth(48)
        self.theme_btn.setToolTip("Cambiar tema")
        self.theme_btn.setStyleSheet(self._theme_btn_style())
        self.theme_btn.clicked.connect(lambda: self.set_theme("light" if CURRENT_THEME=="dark" else "dark"))

        lay.addWidget(self.status_chip)
        lay.addWidget(QLabel("PORT:"))
        lay.addWidget(self.port_combo)
        lay.addWidget(QLabel("BAUD:"))
        lay.addWidget(baud_combo)
        lay.addWidget(ref_btn)
        lay.addWidget(self.conn_btn)
        lay.addWidget(self.sim_btn)
        lay.addWidget(self.theme_btn)
        return hdr

    def _build_tabs(self):
        self.tabs = QTabWidget()
        self.tabs.setTabBar(NoCloseTabBar())
        self.tabs.setStyleSheet(self._tabs_style())
        self.tabs.addTab(self._tab_dashboard(), "⬢  DASHBOARD")
        self.tabs.addTab(self._tab_console(), "⬢  SERIAL MONITOR")
        return self.tabs

    def _tab_dashboard(self):
        tab = QWidget()
        root = QVBoxLayout(tab)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)

        # Fila superior: dos gauges
        gauges_row = QHBoxLayout()
        self.gauge1 = PedalGauge("APPS1 - PRIMARIO")
        self.gauge2 = PedalGauge("APPS2 - SECUNDARIO")
        gauges_row.addWidget(self.gauge1)
        gauges_row.addWidget(self.gauge2)
        root.addLayout(gauges_row, 2)

        # Fila media: diferencia y estado
        mid_row = QHBoxLayout()
        # Panel de plausibilidad
        plaus_frame = QFrame()
        plaus_frame.setStyleSheet(card_style())
        plaus_layout = QVBoxLayout(plaus_frame)
        plaus_layout.setContentsMargins(16, 14, 16, 14)
        plaus_layout.setSpacing(8)
        plaus_title = QLabel("APPS CORRELATION / PLAUSIBILITY")
        plaus_title.setStyleSheet(lbl(C("cyan"), 12, True))
        plaus_layout.addWidget(plaus_title)

        self.apps1_val = QLabel("APPS1: — %")
        self.apps2_val = QLabel("APPS2: — %")
        self.apps1_val.setStyleSheet(lbl(C("text_w"), 12))
        self.apps2_val.setStyleSheet(lbl(C("text_w"), 12))
        plaus_layout.addWidget(self.apps1_val)
        plaus_layout.addWidget(self.apps2_val)

        self.plaus_bar = PlausibilityBar()
        plaus_layout.addWidget(self.plaus_bar)

        mid_row.addWidget(plaus_frame, 1)

        # Panel de estado del sistema
        self.status_panel = APPSStatusPanel()
        mid_row.addWidget(self.status_panel, 1)

        root.addLayout(mid_row, 1)

        # Botones de simulación (visibles solo en modo sim)
        self.sim_btns_frame = QFrame()
        self.sim_btns_frame.setStyleSheet(f"QFrame{{background:{C('bg1')};border-radius:8px;border:1px solid {C('border')};}}")
        sim_btns_layout = QHBoxLayout(self.sim_btns_frame)
        sim_btns_layout.setContentsMargins(8, 6, 8, 6)
        self.sim_test_btns = []
        tests = [("TEST NORMAL", self.sim_mgr.manual_normal),
                 ("TEST TEMP FAULT", self.sim_mgr.manual_temp_fault),
                 ("TEST PLAUSIBILITY FAULT", self.sim_mgr.manual_plausibility_fault),
                 ("TEST APPS1 SHORT", self.sim_mgr.manual_apps1_short),
                 ("TEST APPS2 SHORT", self.sim_mgr.manual_apps2_short),
                 ("RESET SIMULATION", self.sim_mgr.manual_reset)]
        for text, handler in tests:
            btn = QPushButton(text)
            btn.setStyleSheet(btn_style(C("text_w"), C("border")))
            btn.clicked.connect(handler)
            self.sim_test_btns.append(btn)
            sim_btns_layout.addWidget(btn)
        sim_btns_layout.addStretch()
        self.sim_btns_frame.setVisible(False)
        root.addWidget(self.sim_btns_frame)

        # Gráfica temporal
        self.graph = DualLineGraph()
        root.addWidget(self.graph, 1)

        return tab

    def _tab_console(self):
        tab = QWidget()
        root = QVBoxLayout(tab)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("CONSOLA SERIAL", styleSheet=lbl(C("cyan"), 13, True)))
        hdr.addStretch()
        self.msg_count_lbl = QLabel("Mensajes: 0")
        self.msg_count_lbl.setStyleSheet(lbl(C("text_g"), 10))
        hdr.addWidget(self.msg_count_lbl)
        clr = QPushButton("LIMPIAR")
        clr.setFixedWidth(80)
        clr.setStyleSheet(btn_style(C("text_g"), C("border")))
        clr.clicked.connect(lambda: self.console.clear())
        hdr.addWidget(clr)
        root.addLayout(hdr)

        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet(self._console_style())
        root.addWidget(self.console, 1)

        ir = QHBoxLayout()
        self.cmd_input = QLineEdit()
        self.cmd_input.setPlaceholderText("Escribir comando y Enter…")
        self.cmd_input.setStyleSheet(self._cmd_input_style())
        self.cmd_input.returnPressed.connect(self._send_cmd)
        sb = QPushButton("ENVIAR")
        sb.setFixedWidth(90)
        sb.setStyleSheet(btn_style(C("cyan"), C("cyan")))
        sb.clicked.connect(self._send_cmd)
        ir.addWidget(self.cmd_input, 1)
        ir.addWidget(sb)
        root.addLayout(ir)
        return tab

    # ---------- Estilos de componentes ----------
    def _status_chip_style(self):
        if self.serial_mgr.port and self.serial_mgr.port.is_open:
            return f"QLabel{{color:{C('green')};font-size:11px;font-weight:bold;padding:6px 14px;background:{C('bg2')};border-radius:14px;border:1px solid {C('green')}80;}}"
        else:
            return f"QLabel{{color:{C('red')};font-size:11px;font-weight:bold;padding:6px 14px;background:{C('bg2')};border-radius:14px;border:1px solid {C('red')}80;}}"

    def _combo_style(self):
        return f"""QComboBox{{background:{C('bg1')};color:{C('text_w')};border:1px solid {C('border')};
            border-radius:8px;padding:5px 10px;font-size:11px;}}
            QComboBox:hover{{border:1px solid {C('cyan')};}}
            QComboBox QAbstractItemView{{background:{C('bg1')};color:{C('text_w')};
            selection-background-color:{C('bg3')};}}"""

    def _conn_btn_style(self):
        return f"""
            QPushButton{{
                background:{C('bg1')};color:{C('cyan')};border:1.5px solid {C('cyan')};
                border-radius:8px;padding:6px 14px;font-weight:bold;font-size:11px;
            }}
            QPushButton:checked{{
                background:{C('cyan')};color:{C('bg1')};
            }}
            QPushButton:hover{{
                border:1.5px solid {C('gold')};
            }}
        """

    def _sim_btn_style(self):
        return f"""
            QPushButton{{
                background:{C('bg1')};color:{C('text_g')};border:1px solid {C('border')};
                border-radius:8px;padding:6px 10px;font-size:10px;font-weight:bold;
            }}
            QPushButton:checked{{
                background:{C('gold')}20;color:{C('gold')};border:1px solid {C('gold')};
            }}
        """

    def _theme_btn_style(self):
        return f"""
            QPushButton{{
                background:{C('bg2')};color:{C('cyan')};border:1px solid {C('border')};
                border-radius:8px;padding:6px 10px;font-size:12px;font-weight:bold;
            }}
            QPushButton:hover{{
                background:{C('bg3')};border:1px solid {C('cyan')};
            }}
        """

    def _tabs_style(self):
        return f"""
            QTabWidget::pane{{
                border:1px solid {C('border')};border-radius:12px;
                background:{C('bg1')};margin-top:4px;
            }}
            QTabBar::tab{{
                background:{C('bg2')};color:{C('text_g')};padding:10px 26px;min-width:160px;
                font-size:11px;font-weight:bold;
                border-top-left-radius:8px;border-top-right-radius:8px;
                border:1px solid {C('border')};letter-spacing:1px;margin-right:3px;
            }}
            QTabBar::tab:selected{{
                background:{C('bg1')};color:{C('cyan')};border-bottom:2px solid {C('cyan')};
            }}
            QTabBar::tab:hover:!selected{{
                background:{C('bg3')};color:{C('gold')};
            }}
        """

    def _console_style(self):
        return f"""
            QTextEdit{{
                background:{C('bg1')};color:{C('text_w')};border:1px solid {C('border')};
                border-radius:8px;font-size:11px;padding:8px;
            }}
        """

    def _cmd_input_style(self):
        return f"""
            QLineEdit{{
                background:{C('bg1')};color:{C('text_w')};border:1px solid {C('cyan')};
                border-radius:8px;padding:7px 12px;font-size:11px;
            }}
            QLineEdit:focus{{border:1px solid {C('gold')};}}
        """

    # ---------- Lógica de control ----------
    def _refresh_ports(self):
        self.port_combo.clear()
        ports = self.serial_mgr.available_ports()
        for p in (ports if ports else ["Sin puertos"]):
            self.port_combo.addItem(p)

    def _toggle_connection(self, state):
        if state:
            port = self.port_combo.currentText()
            if "Sin" in port or not port:
                self.conn_btn.setChecked(False)
                self.log("⚠ Selecciona un puerto válido")
                return
            if self.serial_mgr.connect(port):
                self.conn_btn.setText("DESCONECTAR")
                self.status_chip.setText("● CONECTADO")
                self.status_chip.setStyleSheet(self._status_chip_style())
            else:
                self.conn_btn.setChecked(False)
        else:
            self.serial_mgr.disconnect()
            self.conn_btn.setText("CONECTAR")
            self.status_chip.setText("● DESCONECTADO")
            self.status_chip.setStyleSheet(self._status_chip_style())

    def _toggle_sim(self, state):
        if state:
            self.sim_btn.setText("SIM ON")
            self.sim_mgr.start()
            self.sim_btns_frame.setVisible(True)
            self.log("▶ Simulación activada")
        else:
            self.sim_btn.setText("SIM OFF")
            self.sim_mgr.stop()
            self.sim_btns_frame.setVisible(False)
            self.log("■ Simulación desactivada")

    def _send_cmd(self):
        txt = self.cmd_input.text().strip()
        if txt:
            # No hay envío serie real en este diseño, pero podemos loguear
            self.log(f"→ {txt}")
            self.cmd_input.clear()

    # ---------- Recepción de datos ----------
    def on_serial_data(self, line):
        self.data_received.emit(line)

    def _parse_legacy_format(self, line):
        """
        Parsea el formato enviado por el ESP32:
        APPS1: 0.415 V | 0.0% || APPS2: 1.251 V | 0.0% || DIF: 0.0% || ESTADO: OK || FALLA: NINGUNA || INTERRUPCION: 0 || MOTOR: ON
        Devuelve un diccionario con las claves estándar (apps1_raw, apps2_raw, apps1_v, apps2_v, apps1_pct, apps2_pct, diff, state, interrupt, motor, fault)
        """
        data = {}

        # Extraer APPS1 voltaje y porcentaje
        m = re.search(r'APPS1:\s*([\d.]+)\s*V\s*\|\s*([\d.]+)%', line)
        if m:
            data['apps1_v'] = float(m.group(1))
            data['apps1_pct'] = float(m.group(2))
            data['apps1_raw'] = 0  # no tenemos raw, ponemos 0

        # APPS2
        m = re.search(r'APPS2:\s*([\d.]+)\s*V\s*\|\s*([\d.]+)%', line)
        if m:
            data['apps2_v'] = float(m.group(1))
            data['apps2_pct'] = float(m.group(2))
            data['apps2_raw'] = 0

        # DIF
        m = re.search(r'DIF:\s*([\d.]+)%', line)
        if m:
            data['diff'] = float(m.group(1))

        # ESTADO
        m = re.search(r'ESTADO:\s*([\w\s]+?)(?:\|\||$)', line)
        if m:
            estado_str = m.group(1).strip()
            if estado_str == "OK":
                data['state'] = "OK"
            elif estado_str == "FALLA PENDIENTE":
                data['state'] = "FAULT_PENDING"
            elif estado_str == "FALLA CONFIRMADA":
                data['state'] = "FAULT_LATCHED"
            else:
                data['state'] = "OK"

        # FALLA
        m = re.search(r'FALLA:\s*([\w\s]+?)(?:\|\||$)', line)
        if m:
            falla_str = m.group(1).strip()
            if falla_str == "NINGUNA":
                data['fault'] = "NONE"
            elif falla_str == "PLAUSIBILIDAD":
                data['fault'] = "PLAUSIBILITY_ERROR"
            elif falla_str == "APPS1 FUERA DE RANGO":
                data['fault'] = "APPS1_OUT_OF_RANGE"
            elif falla_str == "APPS2 FUERA DE RANGO":
                data['fault'] = "APPS2_OUT_OF_RANGE"
            elif falla_str == "APPS1 CORTO A GND":
                data['fault'] = "APPS1_SHORT_GND"
            elif falla_str == "APPS1 CORTO A VCC":
                data['fault'] = "APPS1_SHORT_VCC"
            elif falla_str == "APPS2 CORTO A GND":
                data['fault'] = "APPS2_SHORT_GND"
            elif falla_str == "APPS2 CORTO A VCC":
                data['fault'] = "APPS2_SHORT_VCC"
            else:
                data['fault'] = "NONE"

        # INTERRUPCION
        m = re.search(r'INTERRUPCION:\s*(\d+)', line)
        if m:
            data['interrupt'] = int(m.group(1))

        # MOTOR
        m = re.search(r'MOTOR:\s*(\w+)', line)
        if m:
            motor_str = m.group(1)
            data['motor'] = 1 if motor_str.upper() == "ON" else 0

        return data

    def _dispatch(self, line):
        try:
            self.msg_count += 1
            self.msg_count_lbl.setText(f"Mensajes: {self.msg_count}")
            self.log(f"← {line}")

            # Intentar parsear con el formato estándar (clave:valor con comas)
            data = {}
            if ',' in line and ':' in line:
                parts = line.split(',')
                for part in parts:
                    if ':' not in part:
                        continue
                    k, v = part.split(':', 1)
                    data[k.strip()] = v.strip()
            else:
                # Si no tiene comas, probar con el formato legible del ESP32
                data = self._parse_legacy_format(line)

            # Si no se pudo extraer nada, salir
            if not data:
                return

            # Extraer campos con valores por defecto
            apps1_raw = data.get('apps1_raw', '0')
            apps2_raw = data.get('apps2_raw', '0')
            apps1_v = data.get('apps1_v', '0.0')
            apps2_v = data.get('apps2_v', '0.0')
            apps1_pct = data.get('apps1_pct', '0.0')
            apps2_pct = data.get('apps2_pct', '0.0')
            diff = data.get('diff', '0.0')
            state = data.get('state', 'OK')
            interrupt = data.get('interrupt', '0')
            motor = data.get('motor', '1')
            fault_type = data.get('fault', 'NONE')

            # Actualizar widgets
            self.gauge1.set_value(apps1_pct, apps1_raw, apps1_v)
            self.gauge2.set_value(apps2_pct, apps2_raw, apps2_v)

            self.apps1_val.setText(f"APPS1: {apps1_pct} %")
            self.apps2_val.setText(f"APPS2: {apps2_pct} %")
            self.plaus_bar.set_difference(diff)

            self.status_panel.update_status(state, int(interrupt), int(motor), fault_type)

            if state == "FAULT_LATCHED":
                self.gauge1.set_fault_border(True)
                self.gauge2.set_fault_border(True)
                self.graph.setStyleSheet(f"QWidget{{border:2px solid {C('critical')};}}")
            else:
                self.gauge1.set_fault_border(False)
                self.gauge2.set_fault_border(False)
                self.graph.setStyleSheet("")

            self.graph.push(apps1_pct, apps2_pct)

        except Exception as e:
            self.log(f"⚠ Error procesando línea: {e}")
            self.log(traceback.format_exc().splitlines()[-1])

    # ---------- Log ----------
    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        if "✔" in msg:
            color = C("green")
        elif "✖" in msg or "⚠" in msg:
            color = C("red")
        elif "←" in msg:
            color = C("cyan")
        elif "→" in msg:
            color = C("gold")
        else:
            color = C("text_g")
        self.console.append(
            f'<span style="color:{C("text_g")}">[{ts}]</span> '
            f'<span style="color:{color}">{msg}</span>')
        doc = self.console.document()
        if doc.blockCount() > 1000:
            c = self.console.textCursor()
            c.movePosition(c.Start)
            c.select(c.BlockUnderCursor)
            c.removeSelectedText()
            c.deleteChar()
        self.console.verticalScrollBar().setValue(self.console.verticalScrollBar().maximum())

    def closeEvent(self, ev):
        self.sim_mgr.stop()
        self.serial_mgr.disconnect()
        ev.accept()


class NoCloseTabBar(QTabBar):
    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MiddleButton:
            ev.ignore()
            return
        super().mouseReleaseEvent(ev)


class SafeApplication(QApplication):
    """QApplication que evita cierres inesperados por errores en eventos Qt."""
    def notify(self, receiver, event):
        try:
            return super().notify(receiver, event)
        except Exception as e:
            try:
                print(f"[SAFE_QT] Error capturado: {e}", flush=True)
                traceback.print_exc()
            except Exception:
                pass
            return False


if __name__ == "__main__":
    app = SafeApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont(FONT, 10))
    win = APPSDashboard()
    win.show()
    sys.exit(app.exec_())