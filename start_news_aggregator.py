import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

# ✅ Set DPI scaling policy FIRST before importing anything else that touches QApplication
QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

# ✅ Now import the rest of the modules that might initialize a GUI
from PySide6.QtWidgets import QApplication
import news_aggregator

news_aggregator.launch_app()
