import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QLineEdit, QComboBox, QMessageBox
)
from PySide6.QtCore import Qt

class ManageFeedsTab(QWidget):
    def __init__(self, feeds_file):
        super().__init__()
        self.feeds_file = feeds_file
        self.feeds_data = self.load_feeds()
        self.init_ui()

    def load_feeds(self):
        try:
            with open(self.feeds_file, "r") as file:
                return json.load(file)
        except Exception:
            return {}

    def init_ui(self):
        layout = QVBoxLayout()

        self.category_combo = QComboBox()
        self.category_combo.addItems(sorted(self.feeds_data.keys()))
        self.category_combo.currentIndexChanged.connect(self.load_category_feeds)

        self.feed_list = QListWidget()

        self.feed_name_input = QLineEdit()
        self.feed_name_input.setPlaceholderText("Feed name (e.g., UPI Odd News)")

        self.feed_url_input = QLineEdit()
        self.feed_url_input.setPlaceholderText("Feed URL")

        add_button = QPushButton("Add Feed")
        delete_button = QPushButton("Delete Selected Feed")
        save_button = QPushButton("Save Changes")

        add_button.clicked.connect(self.add_feed)
        delete_button.clicked.connect(self.delete_feed)
        save_button.clicked.connect(self.save_changes)

        layout.addWidget(QLabel("Select Category:"))
        layout.addWidget(self.category_combo)
        layout.addWidget(self.feed_list)
        layout.addWidget(QLabel("Add New Feed:"))
        layout.addWidget(self.feed_name_input)
        layout.addWidget(self.feed_url_input)

        button_row = QHBoxLayout()
        button_row.addWidget(add_button)
        button_row.addWidget(delete_button)
        button_row.addWidget(save_button)
        layout.addLayout(button_row)

        self.setLayout(layout)
        self.load_category_feeds()

    def load_category_feeds(self):
        self.feed_list.clear()
        category = self.category_combo.currentText()
        for feed in self.feeds_data.get(category, []):
            self.feed_list.addItem(f"{feed['name']} — {feed['url']}")

    def add_feed(self):
        name = self.feed_name_input.text().strip()
        url = self.feed_url_input.text().strip()
        category = self.category_combo.currentText()

        if not name or not url:
            QMessageBox.warning(self, "Input Error", "Both name and URL are required.")
            return

        self.feeds_data[category].append({"name": name, "url": url})
        self.feed_name_input.clear()
        self.feed_url_input.clear()
        self.load_category_feeds()

    def delete_feed(self):
        row = self.feed_list.currentRow()
        if row >= 0:
            category = self.category_combo.currentText()
            del self.feeds_data[category][row]
            self.load_category_feeds()

    def save_changes(self):
        try:
            with open(self.feeds_file, "w") as file:
                json.dump(self.feeds_data, file, indent=2)
            QMessageBox.information(self, "Saved", "Feeds saved successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save feeds:\n{e}")
