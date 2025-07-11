import os
import locale

def safe_set_locale():
    """Prevent RecursionError on Windows by safely setting a known good LC_TIME locale."""
    for loc in [
        'English_United States.1252',  # ✅ Windows
        'en_US.UTF-8',                 # ✅ macOS/Linux
        '',                            # ✅ User/system default
        'C'                            # ✅ Last-resort fallback
    ]:
        try:
            locale.setlocale(locale.LC_TIME, loc)
            break
        except locale.Error:
            continue

safe_set_locale()

# ✅ Qt high DPI scaling fix
os.environ["QT_SCALE_FACTOR_ROUNDING_POLICY"] = "PassThrough"

# ✅ Import Qt first so High DPI policy can be set before QApplication is created
from PySide6.QtCore import (
    Qt, QUrl, QSize, QTimer, QRunnable, Slot, QThreadPool, QObject, Signal,
    QTime, QEvent, QRect, QRegularExpression # Added QRegularExpression
)
from PySide6.QtGui import (
    QGuiApplication, QDesktopServices, QPixmap, QIcon, QFont, QTextCharFormat,
    QColor, QIntValidator, QRegularExpressionValidator # Added QRegularExpressionValidator
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton,
    QTabWidget, QListWidget, QListWidgetItem, QTextEdit, QHBoxLayout, QSlider,
    QLineEdit, QComboBox, QMessageBox, QInputDialog, QTreeWidget, QTreeWidgetItem,
    QHeaderView, QFileDialog, QCheckBox, QSpinBox, QSpacerItem, QSizePolicy,
    QTimeEdit, QMenu, QStyledItemDelegate, QAbstractItemView, QDialog
)

# ✅ Set DPI rounding policy BEFORE any QWidget is created
QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

# ✅ Standard Library
import sys
import json
import re
import time
from datetime import datetime, timedelta
from collections import defaultdict
import tempfile
import shutil

# ✅ 3rd Party Libraries
import pytz
import feedparser
import requests

# Constants
FEEDS_FILE = "feeds.json"
SETTINGS_FILE = "settings.json"
REWRITE_OPTIONS_FILE = "rewrite_options.json"
PROFILES_FILE = "character_profiles.json"
RUNDOWN_FILE = "rundown.json"
DEFAULT_FEEDS = [
    {"name": "BBC News - World", "url": "http://feeds.bbci.co.uk/news/world/rss.xml"},
    {"name": "Reuters - Top News", "url": "http://feeds.reuters.com/reuters/topNews"},
    {"name": "The New York Times - Technology", "url": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml"},
    {"name": "CNN - Politics", "url": "http://rss.cnn.com/rss/cnn_politics.rss"},
    {"name": "ESPN - Top", "url": "https://www.espn.com/espn/rss/news"},
]

# Ensure the 'images' directory exists
IMAGES_DIR = "images"
if not os.path.exists(IMAGES_DIR):
    os.makedirs(IMAGES_DIR)

# Worker for fetching stories in a separate thread
class PullStoriesWorker(QRunnable):
    def __init__(self, feeds, story_limit, parent_log_output=None):
        super().__init__()
        self.feeds = feeds
        self.story_limit = story_limit
        self.signals = PullStoriesWorkerSignals()
        self.log_output = parent_log_output
        self.load_settings()
        self.change_font_scale(self.settings.get("font_scale", 0))
        self.local_timezone = pytz.timezone(self.settings.get("timezone", "America/Chicago"))


    @Slot()
    def run(self):
        all_stories = defaultdict(list)
        for feed_info in self.feeds:
            feed_name = feed_info["name"]
            feed_url = feed_info["url"]

            if self.log_output:
                self.signals.log_message.emit(f"Fetching {feed_name} from {feed_url}...")
            else:
                print(f"Fetching {feed_name} from {feed_url}...")

            try:
                # Use requests for more robust fetching with timeout
                response = requests.get(feed_url, timeout=10) # 10-second timeout
                response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
                feed = feedparser.parse(response.content)

                if feed.bozo:
                    if self.log_output:
                        self.signals.log_message.emit(f"Warning: Error parsing {feed_name}: {feed.bozo_exception}")
                    else:
                        print(f"Warning: Error parsing {feed_name}: {feed.bozo_exception}")
                    continue

                for i, entry in enumerate(feed.entries):
                    if i >= self.story_limit:
                        break

                    title = entry.get('title', 'No Title').replace('\n', ' ').strip()
                    link = entry.get('link', '#')
                    summary = entry.get('summary', entry.get('description', 'No Summary')).replace('\n', ' ').strip()
                    published_raw = entry.get('published') or entry.get('updated')
                    published_parsed = None
                    if published_raw:
                        try:
                            # Try parsing with feedparser's parsed_parsed
                            if entry.get('published_parsed'):
                                published_parsed = datetime(*entry.published_parsed[:6])
                            elif entry.get('updated_parsed'):
                                published_parsed = datetime(*entry.updated_parsed[:6])
                            else:
                                # Fallback to manual parsing if feedparser didn't parse it
                                from dateutil import parser as dateparser
                                published_parsed = dateparser.parse(published_raw)
                        except Exception as e:
                            if self.log_output:
                                self.signals.log_message.emit(f"Warning: Could not parse date for '{title}': {e}")
                            else:
                                print(f"Warning: Could not parse date for '{title}': {e}")
                            published_parsed = datetime.now() # Default to now on error
                    else:
                        published_parsed = datetime.now() # Default to now if no date provided

                    # Convert to local timezone for display
                    if published_parsed.tzinfo is None: # Assume UTC if no timezone info
                        published_parsed = pytz.utc.localize(published_parsed)
                    local_tz = pytz.timezone(self.signals.get_local_timezone.emit())
                    published_local = published_parsed.astimezone(local_tz)
                    date_display = published_local.strftime("%Y-%m-%d %H:%M")

                    # Extract image URL
                    image_url = None
                    if 'media_content' in entry and entry.media_content:
                        for media in entry.media_content:
                            if media.get('type', '').startswith('image/'):
                                image_url = media.get('url')
                                break
                    if not image_url and 'media_thumbnail' in entry and entry.media_thumbnail:
                        if isinstance(entry.media_thumbnail, list) and entry.media_thumbnail:
                            image_url = entry.media_thumbnail[0].get('url')
                        elif isinstance(entry.media_thumbnail, dict):
                            image_url = entry.media_thumbnail.get('url')

                    if not image_url and 'links' in entry:
                        for link_item in entry.links:
                            if link_item.get('rel') == 'enclosure' and link_item.get('type', '').startswith('image/'):
                                image_url = link_item.get('href')
                                break
                    
                    # Basic categorization based on feed name
                    category = "Other"
                    if "technology" in feed_name.lower():
                        category = "Technology"
                    elif "sports" in feed_name.lower():
                        category = "Sports"
                    elif "politics" in feed_name.lower():
                        category = "Politics"
                    elif "world" in feed_name.lower() or "international" in feed_name.lower():
                        category = "World News"
                    elif "business" in feed_name.lower():
                        category = "Business"
                    elif "entertainment" in feed_name.lower():
                        category = "Entertainment"
                    # Add more categories as needed

                    all_stories[category].append({
                        "title": title,
                        "link": link,
                        "summary": summary,
                        "source": feed_name,
                        "pub_date": date_display,
                        "image_url": image_url,
                        "category": category, # Store category with story
                        "rewritten": False, # Flag for rewrite status
                        "original_summary": summary # Store original for reference
                    })
                if self.log_output:
                    self.signals.log_message.emit(f"Finished fetching {feed_name}.")
                else:
                    print(f"Finished fetching {feed_name}.")

            except requests.exceptions.RequestException as e:
                if self.log_output:
                    self.signals.log_message.emit(f"Error fetching {feed_name} from {feed_url}: {e}")
                else:
                    print(f"Error fetching {feed_name} from {feed_url}: {e}")
            except Exception as e:
                if self.log_output:
                    self.signals.log_message.emit(f"An unexpected error occurred for {feed_name}: {e}")
                else:
                    print(f"An unexpected error occurred for {feed_name}: {e}")

        self.signals.stories_ready.emit(all_stories)

class PullStoriesWorkerSignals(QObject):
    stories_ready = Signal(dict)
    log_message = Signal(str)
    get_local_timezone = Signal(str) # Signal to request local timezone from main thread

class RundownItemDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, tree_widget=None):
        super().__init__(parent)
        self.tree_widget = tree_widget
        self.edit_mode = False
        self.duration_validator = QRegularExpressionValidator(QRegularExpression(r"^\d{1,2}:\d{2}$")) # HH:MM or H:MM or MM:SS or M:SS
        self.text_height_cache = {} # Cache for text height calculations

    def createEditor(self, parent, option, index):
        if index.column() == 2:  # Duration column
            editor = QLineEdit(parent)
            editor.setValidator(self.duration_validator)
            self.edit_mode = True
            return editor
        elif index.column() == 3: # Backtime column (QTimeEdit)
            editor = QTimeEdit(parent)
            editor.setDisplayFormat("h:mm AP")
            editor.setCalendarPopup(False)
            self.edit_mode = True
            return editor
        elif index.column() == 0: # Headline column
            # Use a QTextEdit for multi-line editing
            editor = QTextEdit(parent)
            self.edit_mode = True
            return editor
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        if index.column() == 2:  # Duration column
            value = index.model().data(index, Qt.EditRole)
            editor.setText(value)
        elif index.column() == 3: # Backtime column
            value = index.model().data(index, Qt.EditRole)
            if value:
                time_obj = datetime.strptime(value, "%I:%M %p").time() if "AM" in value or "PM" in value else datetime.strptime(value, "%H:%M").time()
                editor.setTime(time_obj)
            else:
                editor.setTime(QTime(0, 0)) # Default to 00:00
        elif index.column() == 0: # Headline column
            editor.setText(index.model().data(index, Qt.EditRole))
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        if index.column() == 2:  # Duration column
            text = editor.text()
            if self.duration_validator.validate(text, 0)[0] == QRegularExpressionValidator.Acceptable:
                model.setData(index, text, Qt.EditRole)
            else:
                # Optionally revert or show error if invalid
                pass
        elif index.column() == 3: # Backtime column
            model.setData(index, editor.time().toString("h:mm AP"), Qt.EditRole)
        elif index.column() == 0: # Headline column
            model.setData(index, editor.toPlainText(), Qt.EditRole)
        else:
            super().setModelData(editor, model, index)
        self.edit_mode = False # Exit edit mode

    def updateEditorGeometry(self, editor, option, index):
        if index.column() == 0: # Headline column
            editor.setGeometry(option.rect)
        else:
            super().updateEditorGeometry(editor, option, index)

    def sizeHint(self, option, index):
        if index.column() == 0: # Headline column
            # Calculate height based on content
            text = index.data(Qt.DisplayRole)
            if not text:
                return super().sizeHint(option, index)

            # Use a cache to avoid re-calculating for the same text
            if text in self.text_height_cache:
                return QSize(option.rect.width(), self.text_height_cache[text])

            document = QTextDocument()
            document.setDefaultFont(option.font)
            document.setHtml(text) # Or setText if not rich text
            document.setTextWidth(option.rect.width()) # Constrain width

            height = int(document.size().height()) + 10 # Add some padding
            self.text_height_cache[text] = height
            return QSize(option.rect.width(), height)

        return super().sizeHint(option, index)

class NewsAggregatorApp(QMainWindow):
    def __init__(self):
        super().__init__()

        # ✅ Load settings once
        loaded = self.load_settings()
        self.settings = loaded if loaded is not None else {
            "dark_mode": False,
            "font_scale": 0,
            "timezone": "America/Chicago"
        }

        QTimer.singleShot(0, self.apply_saved_font_scale)

        self.setWindowTitle("News Aggregator")
        self.filter_category_dropdown = QComboBox()
        self.teleprompter_text_edit = QTextEdit()
        self.teleprompter_text_edit.setReadOnly(True)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.statusBar().showMessage("Ready")
        self.threadpool = QThreadPool()

        self.apply_dark_mode(self.settings.get("dark_mode", False))

        self.character_profiles = self.load_profiles()
        self.rewrite_options = self.load_rewrite_options()
        self.style_definitions = self.rewrite_options.get("Style", {})
        self.tone_definitions = self.rewrite_options.get("Tone", {})
        self.length_definitions = self.rewrite_options.get("Length", {})

        self.profile_tooltips = {
            name: profile.get("description", "")
            for name, profile in self.character_profiles.items()
        }

        self.current_expanded_item = None
        self.current_rundown_filename = None
        self._recalculating_backtimes = False

        self.setup_settings_tab()
        self.setup_feed_manager_tab()
        self.setup_articles_tab()
        self.setup_rundown_tab()

        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.installEventFilter(self)
        self.showMaximized()


    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape and self.tabs.currentIndex() == self.tabs.indexOf(self.rundown_tab):
            if self.rundown_delegate.edit_mode:
                # If in edit mode, discard changes and exit edit
                self.rundown_tree.closePersistentEditor(self.rundown_tree.currentIndex())
                self.rundown_delegate.edit_mode = False
                return True # Event handled
        return super().eventFilter(obj, event)

    def load_profiles(self):
        try:
            with open(PROFILES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {
                "Default Narrator": {
                    "description": "A standard, objective news narrator.",
                    "prompt": "You are an objective news narrator."
                },
                "Sarcastic Reporter": {
                    "description": "A reporter with a cynical and sarcastic tone.",
                    "prompt": "You are a cynical and sarcastic news reporter."
                }
            }
        except json.JSONDecodeError:
            QMessageBox.warning(self, "Error", f"Could not parse {PROFILES_FILE}. Creating new default.")
            return {
                "Default Narrator": {
                    "description": "A standard, objective news narrator.",
                    "prompt": "You are an objective news narrator."
                },
                "Sarcastic Reporter": {
                    "description": "A reporter with a cynical and sarcastic tone.",
                    "prompt": "You are a cynical and sarcastic news reporter."
                }
            }

    def save_profiles(self):
        try:
            with open(PROFILES_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.character_profiles, f, indent=4)
        except IOError as e:
            QMessageBox.critical(self, "Save Error", f"Could not save character profiles: {e}")

    def load_rewrite_options(self):
        try:
            with open(REWRITE_OPTIONS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {
                "Style": {
                    "Standard": "Rewrite in a standard, journalistic style.",
                    "Conversational": "Rewrite in a conversational, informal style.",
                    "Academic": "Rewrite in a formal, academic style with precise language."
                },
                "Tone": {
                    "Objective": "Maintain a neutral and objective tone.",
                    "Humorous": "Inject humor and wit into the summary.",
                    "Serious": "Maintain a serious and grave tone."
                },
                "Length": {
                    "Concise": "Make the summary very brief (around 50 words).",
                    "Standard": "Make the summary a standard length (around 150 words).",
                    "Detailed": "Provide a detailed summary (around 300 words)."
                }
            }
        except json.JSONDecodeError:
            QMessageBox.warning(self, "Error", f"Could not parse {REWRITE_OPTIONS_FILE}. Creating new default.")
            return {
                "Style": {
                    "Standard": "Rewrite in a standard, journalistic style.",
                    "Conversational": "Rewrite in a conversational, informal style.",
                    "Academic": "Rewrite in a formal, academic style with precise language."
                },
                "Tone": {
                    "Objective": "Maintain a neutral and objective tone.",
                    "Humorous": "Inject humor and wit into the summary.",
                    "Serious": "Maintain a serious and grave tone."
                },
                "Length": {
                    "Concise": "Make the summary very brief (around 50 words).",
                    "Standard": "Make the summary a standard length (around 150 words).",
                    "Detailed": "Provide a detailed summary (around 300 words)."
                }
            }

    def save_rewrite_options(self):
        try:
            with open(REWRITE_OPTIONS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.rewrite_options, f, indent=4)
        except IOError as e:
            QMessageBox.critical(self, "Save Error", f"Could not save rewrite options: {e}")

    def load_settings(self):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {"dark_mode": False, "font_scale": 0, "timezone": "America/Chicago"} # Default settings
        except json.JSONDecodeError:
            QMessageBox.warning(self, "Error", f"Could not parse {SETTINGS_FILE}. Resetting settings.")
            return {"dark_mode": False, "font_scale": 0, "timezone": "America/Chicago"} # Default settings

    def save_settings(self):
        self.settings["dark_mode"] = self.dark_mode_checkbox.isChecked()
        self.settings["font_scale"] = self.font_scale_spinbox.value()
        self.settings["timezone"] = self.timezone_combo.currentText()
        self.settings["profiles"] = self.character_profiles
        self.settings["rewrite_options"] = self.rewrite_options

        try:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=4, ensure_ascii=False)
            self.statusBar().showMessage("✅ Settings saved", 3000)
        except IOError as e:
            QMessageBox.critical(self, "Save Error", f"Could not save settings: {e}")

    def load_settings(self):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                self.settings = json.load(f)
        except (IOError, json.JSONDecodeError):
            self.settings = {}


    def apply_dark_mode(self, enabled):
        self.settings["dark_mode"] = enabled
        if enabled:
            self.setStyleSheet("""
                QMainWindow {
                    background-color: #2e2e2e;
                    color: #f0f0f0;
                }
                QTabWidget::pane {
                    border: 1px solid #444;
                }
                QTabBar::tab {
                    background: #3a3a3a;
                    color: #f0f0f0;
                    border: 1px solid #444;
                    border-bottom-color: #3a3a3a;
                    padding: 8px;
                }
                QTabBar::tab:selected {
                    background: #2e2e2e;
                    border-bottom-color: #2e2e2e;
                }
                QListWidget, QTextEdit, QLineEdit, QComboBox, QTreeWidget, QSpinBox, QTimeEdit {
                    background-color: #3a3a3a;
                    color: #f0f0f0;
                    border: 1px solid #555;
                }
                QPushButton {
                    background-color: #555;
                    color: #f0f0f0;
                    border: 1px solid #666;
                    padding: 5px 10px;
                }
                QPushButton:hover {
                    background-color: #666;
                }
                QLabel {
                    color: #f0f0f0;
                }
                QHeaderView::section {
                    background-color: #4a4a4a;
                    color: #f0f0f0;
                    padding: 4px;
                    border: 1px solid #555;
                }
                QMessageBox {
                    background-color: #2e2e2e;
                    color: #f0f0f0;
                }
                QMessageBox QLabel {
                    color: #f0f0f0;
                }
                QMessageBox QPushButton {
                    background-color: #555;
                    color: #f0f0f0;
                }
                QMenu {
                    background-color: #3a3a3a;
                    color: #f0f0f0;
                    border: 1px solid #555;
                }
                QMenu::item:selected {
                    background-color: #555;
                }
                QListView::item:selected {
                    background-color: #0078d7; /* Standard selection blue */
                    color: white;
                }
                QTreeWidget::item:selected {
                    background-color: #0078d7; /* Standard selection blue */
                    color: white;
                }
            """)
        else:
            self.setStyleSheet("") # Clear stylesheet for light mode

    def apply_saved_font_scale(self):
        font_scale = self.settings.get("font_scale", 0)
        default_font = QApplication.font()
        # Use the already initialized teleprompter_text_edit
        self.teleprompter_text_edit.setFont(QFont("Arial", default_font.pointSize() + 5 + font_scale)) # Larger for teleprompter

        # Apply to general application font if not 0
        if font_scale != 0:
            new_font = QFont(default_font.family(), default_font.pointSize() + font_scale)
            QApplication.setFont(new_font)
        else:
            # Reset to system default if scale is 0
            QApplication.setFont(QGuiApplication.font())

    def closeEvent(self, event):
        self.settings["dark_mode"] = self.dark_mode_checkbox.isChecked()
        self.settings["font_scale"] = self.font_scale_spinbox.value()
        self.settings["timezone"] = self.timezone_combo.currentText()
        self.save_settings()
        event.accept()


    def setup_settings_tab(self):
        self.settings_tab = QWidget()
        layout = QVBoxLayout(self.settings_tab)

        # Dark Mode Toggle
        dark_mode_layout = QHBoxLayout()
        dark_mode_label = QLabel("Dark Mode:")
        self.dark_mode_checkbox = QCheckBox()
        self.dark_mode_checkbox.setChecked(self.settings.get("dark_mode", False))
        self.dark_mode_checkbox.stateChanged.connect(lambda state: self.apply_dark_mode(state == Qt.Checked))
        dark_mode_layout.addWidget(dark_mode_label)
        dark_mode_layout.addWidget(self.dark_mode_checkbox)
        dark_mode_layout.addStretch()
        layout.addLayout(dark_mode_layout)

        # Font Scaling
        font_scale_layout = QHBoxLayout()
        font_scale_label = QLabel("Font Scale:")
        self.font_scale_spinbox = QSpinBox()
        self.font_scale_spinbox.setMinimum(-5)
        self.font_scale_spinbox.setMaximum(5)
        self.font_scale_spinbox.setValue(self.settings.get("font_scale", 0))
        self.font_scale_spinbox.valueChanged.connect(self.change_font_scale)
        font_scale_layout.addWidget(font_scale_label)
        font_scale_layout.addWidget(self.font_scale_spinbox)
        font_scale_layout.addStretch()
        layout.addLayout(font_scale_layout)

        # Timezone Setting
        timezone_layout = QHBoxLayout()
        timezone_label = QLabel("Local Timezone:")
        self.timezone_combo = QComboBox()
        # Populate with common timezones
        for tz in pytz.common_timezones:
            self.timezone_combo.addItem(tz)
        current_tz = self.settings.get("timezone", "America/Chicago")
        self.timezone_combo.setCurrentText(current_tz)
        self.timezone_combo.currentTextChanged.connect(self.change_timezone)
        timezone_layout.addWidget(timezone_label)
        timezone_layout.addWidget(self.timezone_combo)
        timezone_layout.addStretch()
        layout.addLayout(timezone_layout)

        # Add profile management section
        layout.addWidget(QLabel("<h2>Character Profiles</h2>"))
        self.profile_list = QListWidget()
        self.profile_list.currentItemChanged.connect(self.display_profile_details)
        layout.addWidget(self.profile_list)

        profile_buttons_layout = QHBoxLayout()
        self.add_profile_button = QPushButton("Add Profile")
        self.add_profile_button.clicked.connect(self.add_profile)
        self.edit_profile_button = QPushButton("Edit Profile")
        self.edit_profile_button.clicked.connect(self.edit_profile)
        self.delete_profile_button = QPushButton("Delete Profile")
        self.delete_profile_button.clicked.connect(self.delete_profile)
        profile_buttons_layout.addWidget(self.add_profile_button)
        profile_buttons_layout.addWidget(self.edit_profile_button)
        profile_buttons_layout.addWidget(self.delete_profile_button)
        layout.addLayout(profile_buttons_layout)

        self.profile_name_edit = QLineEdit()
        self.profile_name_edit.setPlaceholderText("Profile Name")
        self.profile_prompt_edit = QTextEdit()
        self.profile_prompt_edit.setPlaceholderText("Profile Prompt for AI")
        self.profile_description_edit = QLineEdit()
        self.profile_description_edit.setPlaceholderText("Short Description (for tooltip)")

        layout.addWidget(QLabel("Profile Name:"))
        layout.addWidget(self.profile_name_edit)
        layout.addWidget(QLabel("Profile Prompt:"))
        layout.addWidget(self.profile_prompt_edit)
        layout.addWidget(QLabel("Profile Description:"))
        layout.addWidget(self.profile_description_edit)

        # Add rewrite options management section
        layout.addWidget(QLabel("<h2>Rewrite Options</h2>"))
        rewrite_options_layout = QVBoxLayout()

        # Style Options
        self.style_list_widget = QListWidget()
        self.style_list_widget.currentItemChanged.connect(lambda: self.display_rewrite_option_details("Style", self.style_list_widget))
        rewrite_options_layout.addWidget(QLabel("<h3>Styles</h3>"))
        rewrite_options_layout.addWidget(self.style_list_widget)

        style_buttons_layout = QHBoxLayout()
        self.add_style_button = QPushButton("Add Style")
        self.add_style_button.clicked.connect(lambda: self.add_rewrite_option("Style"))
        self.edit_style_button = QPushButton("Edit Style")
        self.edit_style_button.clicked.connect(lambda: self.edit_rewrite_option("Style", self.style_list_widget))
        self.delete_style_button = QPushButton("Delete Style")
        self.delete_style_button.clicked.connect(lambda: self.delete_rewrite_option("Style", self.style_list_widget))
        style_buttons_layout.addWidget(self.add_style_button)
        style_buttons_layout.addWidget(self.edit_style_button)
        style_buttons_layout.addWidget(self.delete_style_button)
        rewrite_options_layout.addLayout(style_buttons_layout)

        # Tone Options
        self.tone_list_widget = QListWidget()
        self.tone_list_widget.currentItemChanged.connect(lambda: self.display_rewrite_option_details("Tone", self.tone_list_widget))
        rewrite_options_layout.addWidget(QLabel("<h3>Tones</h3>"))
        rewrite_options_layout.addWidget(self.tone_list_widget)

        tone_buttons_layout = QHBoxLayout()
        self.add_tone_button = QPushButton("Add Tone")
        self.add_tone_button.clicked.connect(lambda: self.add_rewrite_option("Tone"))
        self.edit_tone_button = QPushButton("Edit Tone")
        self.edit_tone_button.clicked.connect(lambda: self.edit_rewrite_option("Tone", self.tone_list_widget))
        self.delete_tone_button = QPushButton("Delete Tone")
        self.delete_tone_button.clicked.connect(lambda: self.delete_rewrite_option("Tone", self.tone_list_widget))
        tone_buttons_layout.addWidget(self.add_tone_button)
        tone_buttons_layout.addWidget(self.edit_tone_button)
        tone_buttons_layout.addWidget(self.delete_tone_button)
        rewrite_options_layout.addLayout(tone_buttons_layout)

        # Length Options
        self.length_list_widget = QListWidget()
        self.length_list_widget.currentItemChanged.connect(lambda: self.display_rewrite_option_details("Length", self.length_list_widget))
        rewrite_options_layout.addWidget(QLabel("<h3>Lengths</h3>"))
        rewrite_options_layout.addWidget(self.length_list_widget)

        length_buttons_layout = QHBoxLayout()
        self.add_length_button = QPushButton("Add Length")
        self.add_length_button.clicked.connect(lambda: self.add_rewrite_option("Length"))
        self.edit_length_button = QPushButton("Edit Length")
        self.edit_length_button.clicked.connect(lambda: self.edit_rewrite_option("Length", self.length_list_widget))
        self.delete_length_button = QPushButton("Delete Length")
        self.delete_length_button.clicked.connect(lambda: self.delete_rewrite_option("Length", self.length_list_widget))
        length_buttons_layout.addWidget(self.add_length_button)
        length_buttons_layout.addWidget(self.edit_length_button)
        length_buttons_layout.addWidget(self.delete_length_button)
        rewrite_options_layout.addLayout(length_buttons_layout)

        self.rewrite_option_name_edit = QLineEdit()
        self.rewrite_option_name_edit.setPlaceholderText("Option Name")
        self.rewrite_option_description_edit = QTextEdit()
        self.rewrite_option_description_edit.setPlaceholderText("Option Description for AI")

        rewrite_options_layout.addWidget(QLabel("Option Name:"))
        rewrite_options_layout.addWidget(self.rewrite_option_name_edit)
        rewrite_options_layout.addWidget(QLabel("Option Description:"))
        rewrite_options_layout.addWidget(self.rewrite_option_description_edit)

        layout.addLayout(rewrite_options_layout)

        # Save settings when user changes inputs
        self.dark_mode_checkbox.stateChanged.connect(self.save_settings)
        self.font_scale_spinbox.valueChanged.connect(self.save_settings)
        self.timezone_combo.currentTextChanged.connect(self.save_settings)

        layout.addStretch() # Pushes all content to the top
        self.tabs.addTab(self.settings_tab, "Settings")
        self.populate_profile_list()
        self.populate_rewrite_option_lists()

    def change_font_scale(self, value):
        self.settings["font_scale"] = value
        self.save_settings()
        self.apply_saved_font_scale() # Re-apply font scale

    def change_timezone(self, timezone_str):
        self.settings["timezone"] = timezone_str
        self.save_settings()

    def populate_profile_list(self):
        self.profile_list.clear()
        for name in self.character_profiles.keys():
            item = QListWidgetItem(name)
            self.profile_list.addItem(item)
        if self.profile_list.count() > 0:
            self.profile_list.setCurrentRow(0)

    def display_profile_details(self, current_item, previous_item):
        if current_item:
            profile_name = current_item.text()
            profile = self.character_profiles.get(profile_name, {})
            self.profile_name_edit.setText(profile_name)
            self.profile_prompt_edit.setText(profile.get("prompt", ""))
            self.profile_description_edit.setText(profile.get("description", ""))
        else:
            self.profile_name_edit.clear()
            self.profile_prompt_edit.clear()
            self.profile_description_edit.clear()

    def add_profile(self):
        name = self.profile_name_edit.text().strip()
        prompt = self.profile_prompt_edit.toPlainText().strip()
        description = self.profile_description_edit.text().strip()

        if not name:
            QMessageBox.warning(self, "Input Error", "Profile name cannot be empty.")
            return

        if name in self.character_profiles:
            QMessageBox.warning(self, "Duplicate Profile", f"Profile '{name}' already exists. Use 'Edit Profile' to modify.")
            return

        self.character_profiles[name] = {"prompt": prompt, "description": description}
        self.profile_tooltips[name] = description # Update tooltip cache
        self.save_profiles()
        self.populate_profile_list()
        self.profile_list.setCurrentItem(self.profile_list.findItems(name, Qt.MatchExactly)[0])

    def edit_profile(self):
        current_item = self.profile_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Selection Error", "Please select a profile to edit.")
            return

        original_name = current_item.text()
        new_name = self.profile_name_edit.text().strip()
        new_prompt = self.profile_prompt_edit.toPlainText().strip()
        new_description = self.profile_description_edit.text().strip()

        if not new_name:
            QMessageBox.warning(self, "Input Error", "Profile name cannot be empty.")
            return

        if original_name != new_name and new_name in self.character_profiles:
            QMessageBox.warning(self, "Duplicate Profile", f"Profile '{new_name}' already exists.")
            return

        # If name changed, delete old entry and add new one
        if original_name != new_name:
            del self.character_profiles[original_name]
            if original_name in self.profile_tooltips:
                del self.profile_tooltips[original_name]

        self.character_profiles[new_name] = {"prompt": new_prompt, "description": new_description}
        self.profile_tooltips[new_name] = new_description
        self.save_profiles()
        self.populate_profile_list()
        self.profile_list.setCurrentItem(self.profile_list.findItems(new_name, Qt.MatchExactly)[0])

    def delete_profile(self):
        current_item = self.profile_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Selection Error", "Please select a profile to delete.")
            return

        profile_name = current_item.text()
        reply = QMessageBox.question(self, "Delete Profile",
                                     f"Are you sure you want to delete profile '{profile_name}'?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            del self.character_profiles[profile_name]
            if profile_name in self.profile_tooltips:
                del self.profile_tooltips[profile_name]
            self.save_profiles()
            self.populate_profile_list()

    def populate_rewrite_option_lists(self):
        self.style_list_widget.clear()
        for name in self.style_definitions.keys():
            self.style_list_widget.addItem(name)
        if self.style_list_widget.count() > 0:
            self.style_list_widget.setCurrentRow(0)

        self.tone_list_widget.clear()
        for name in self.tone_definitions.keys():
            self.tone_list_widget.addItem(name)
        if self.tone_list_widget.count() > 0:
            self.tone_list_widget.setCurrentRow(0)

        self.length_list_widget.clear()
        for name in self.length_definitions.keys():
            self.length_list_widget.addItem(name)
        if self.length_list_widget.count() > 0:
            self.length_list_widget.setCurrentRow(0)

    def display_rewrite_option_details(self, option_type, list_widget):
        current_item = list_widget.currentItem()
        definitions = getattr(self, f"{option_type.lower()}_definitions")
        if current_item:
            option_name = current_item.text()
            description = definitions.get(option_name, "")
            self.rewrite_option_name_edit.setText(option_name)
            self.rewrite_option_description_edit.setText(description)
        else:
            self.rewrite_option_name_edit.clear()
            self.rewrite_option_description_edit.clear()

    def add_rewrite_option(self, option_type):
        name = self.rewrite_option_name_edit.text().strip()
        description = self.rewrite_option_description_edit.toPlainText().strip()
        definitions = getattr(self, f"{option_type.lower()}_definitions")
        list_widget = getattr(self, f"{option_type.lower()}_list_widget")

        if not name:
            QMessageBox.warning(self, "Input Error", "Option name cannot be empty.")
            return
        if name in definitions:
            QMessageBox.warning(self, "Duplicate Option", f"Option '{name}' already exists. Use 'Edit' to modify.")
            return

        definitions[name] = description
        self.save_rewrite_options()
        self.populate_rewrite_option_lists()
        list_widget.setCurrentItem(list_widget.findItems(name, Qt.MatchExactly)[0])

    def edit_rewrite_option(self, option_type, list_widget):
        current_item = list_widget.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Selection Error", f"Please select a {option_type} option to edit.")
            return

        original_name = current_item.text()
        new_name = self.rewrite_option_name_edit.text().strip()
        new_description = self.rewrite_option_description_edit.toPlainText().strip()
        definitions = getattr(self, f"{option_type.lower()}_definitions")

        if not new_name:
            QMessageBox.warning(self, "Input Error", "Option name cannot be empty.")
            return
        if original_name != new_name and new_name in definitions:
            QMessageBox.warning(self, "Duplicate Option", f"Option '{new_name}' already exists.")
            return

        if original_name != new_name:
            del definitions[original_name]
        definitions[new_name] = new_description
        self.save_rewrite_options()
        self.populate_rewrite_option_lists()
        list_widget.setCurrentItem(list_widget.findItems(new_name, Qt.MatchExactly)[0])

    def delete_rewrite_option(self, option_type, list_widget):
        current_item = list_widget.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Selection Error", f"Please select a {option_type} option to delete.")
            return

        option_name = current_item.text()
        reply = QMessageBox.question(self, "Delete Option",
                                     f"Are you sure you want to delete '{option_name}'?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            definitions = getattr(self, f"{option_type.lower()}_definitions")
            del definitions[option_name]
            self.save_rewrite_options()
            self.populate_rewrite_option_lists()

    def setup_feed_manager_tab(self):
        self.feed_manager_tab = QWidget()
        layout = QVBoxLayout(self.feed_manager_tab)

        self.feed_list = QListWidget()
        self.feed_list.currentItemChanged.connect(self.display_feed_details)
        layout.addWidget(self.feed_list)

        form_layout = QVBoxLayout()
        self.feed_name_edit = QLineEdit()
        self.feed_name_edit.setPlaceholderText("Feed Name")
        self.feed_url_edit = QLineEdit()
        self.feed_url_edit.setPlaceholderText("Feed URL")

        form_layout.addWidget(QLabel("Feed Name:"))
        form_layout.addWidget(self.feed_name_edit)
        form_layout.addWidget(QLabel("Feed URL:"))
        form_layout.addWidget(self.feed_url_edit)
        layout.addLayout(form_layout)

        buttons_layout = QHBoxLayout()
        self.add_feed_button = QPushButton("Add Feed")
        self.add_feed_button.clicked.connect(self.add_feed)
        self.edit_feed_button = QPushButton("Edit Feed")
        self.edit_feed_button.clicked.connect(self.edit_feed)
        self.delete_feed_button = QPushButton("Delete Feed")
        self.delete_feed_button.clicked.connect(self.delete_feed)

        buttons_layout.addWidget(self.add_feed_button)
        buttons_layout.addWidget(self.edit_feed_button)
        buttons_layout.addWidget(self.delete_feed_button)
        layout.addLayout(buttons_layout)

        layout.addStretch()

        self.tabs.addTab(self.feed_manager_tab, "Feed Manager")
        self.load_feeds_from_file() # Load feeds initially

    def load_feeds_from_file(self):
        try:
            with open(FEEDS_FILE, 'r', encoding='utf-8') as f:
                feeds = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            feeds = DEFAULT_FEEDS
            self.save_feeds_to_file(feeds) # Save defaults if file not found or invalid JSON

        self.feed_list.clear()
        for feed in feeds:
            item = QListWidgetItem(feed["name"])
            item.setData(Qt.UserRole, feed["url"]) # Store URL in UserRole
            self.feed_list.addItem(item)
        if self.feed_list.count() > 0:
            self.feed_list.setCurrentRow(0)

        # Clear and re-populate the filter_category_dropdown
        # This widget is now initialized in __init__
        self.filter_category_dropdown.clear()
        self.filter_category_dropdown.addItems(["All", "Technology", "Sports", "Politics", "World News", "Business", "Entertainment"])
        # You might want to update categories dynamically based on loaded feeds later.

    def save_feeds_to_file(self, feeds):
        try:
            with open(FEEDS_FILE, 'w', encoding='utf-8') as f:
                json.dump(feeds, f, indent=4)
        except IOError as e:
            QMessageBox.critical(self, "Save Error", f"Could not save feeds: {e}")

    def display_feed_details(self, current_item, previous_item):
        if current_item:
            self.feed_name_edit.setText(current_item.text())
            self.feed_url_edit.setText(current_item.data(Qt.UserRole))
        else:
            self.feed_name_edit.clear()
            self.feed_url_edit.clear()

    def add_feed(self):
        name = self.feed_name_edit.text().strip()
        url = self.feed_url_edit.text().strip()

        if not name or not url:
            QMessageBox.warning(self, "Input Error", "Feed name and URL cannot be empty.")
            return

        feeds = self.get_current_feeds()
        for feed in feeds:
            if feed["name"] == name:
                QMessageBox.warning(self, "Duplicate Feed", f"Feed '{name}' already exists.")
                return

        feeds.append({"name": name, "url": url})
        self.save_feeds_to_file(feeds)
        self.load_feeds_from_file() # Reload list to show new feed
        self.feed_list.setCurrentItem(self.feed_list.findItems(name, Qt.MatchExactly)[0]) # Select new feed

    def edit_feed(self):
        current_item = self.feed_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Selection Error", "Please select a feed to edit.")
            return

        original_name = current_item.text()
        new_name = self.feed_name_edit.text().strip()
        new_url = self.feed_url_edit.text().strip()

        if not new_name or not new_url:
            QMessageBox.warning(self, "Input Error", "Feed name and URL cannot be empty.")
            return

        feeds = self.get_current_feeds()
        for feed in feeds:
            if feed["name"] == original_name:
                feed["name"] = new_name
                feed["url"] = new_url
                break
        self.save_feeds_to_file(feeds)
        self.load_feeds_from_file() # Reload list
        self.feed_list.setCurrentItem(self.feed_list.findItems(new_name, Qt.MatchExactly)[0]) # Select updated feed


    def delete_feed(self):
        current_item = self.feed_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Selection Error", "Please select a feed to delete.")
            return

        feed_name = current_item.text()
        reply = QMessageBox.question(self, "Delete Feed",
                                     f"Are you sure you want to delete feed '{feed_name}'?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            feeds = [f for f in self.get_current_feeds() if f["name"] != feed_name]
            self.save_feeds_to_file(feeds)
            self.load_feeds_from_file() # Reload list

    def get_current_feeds(self):
        feeds = []
        for i in range(self.feed_list.count()):
            item = self.feed_list.item(i)
            feeds.append({"name": item.text(), "url": item.data(Qt.UserRole)})
        return feeds

    def setup_articles_tab(self):
        self.articles_tab = QWidget()
        layout = QVBoxLayout()

        # Top controls
        controls_row_top = QHBoxLayout()
        self.slider_label = QLabel("Stories per feed: 10")
        self.story_limit_slider = QSlider(Qt.Horizontal)
        self.story_limit_slider.setMinimum(1)
        self.story_limit_slider.setMaximum(50)
        self.story_limit_slider.setValue(10)
        self.story_limit_slider.setFixedWidth(300)
        self.story_limit_slider.valueChanged.connect(
            lambda val: self.slider_label.setText(f"Stories per feed: {val}")
        )

        # Add filter category dropdown here
        filter_category_label = QLabel("Category:")
        # self.filter_category_dropdown is already initialized in __init__
        self.filter_category_dropdown.addItems(["All", "Technology", "Sports", "Politics", "World News", "Business", "Entertainment"]) # Adjust categories as needed
        self.filter_category_dropdown.currentIndexChanged.connect(self.filter_articles) # Connect to your filtering logic

        self.pull_button = QPushButton("Pull Stories")
        self.pull_button.clicked.connect(self.pull_stories)

        controls_row_top.addWidget(self.slider_label)
        controls_row_top.addWidget(self.story_limit_slider)
        controls_row_top.addSpacing(20) # Add some space
        controls_row_top.addWidget(filter_category_label)
        controls_row_top.addWidget(self.filter_category_dropdown)
        controls_row_top.addStretch()
        controls_row_top.addWidget(self.pull_button)

        # Tree setup
        self.articles_tree = QTreeWidget()
        self.articles_tree.setColumnCount(3)
        self.articles_tree.setHeaderLabels(["Headline", "Source", "Date"])

        self.articles_tree.setIconSize(QSize(80, 80)) # Reduces size to prevent encroaching on checkbox

        self.articles_tree.setStyleSheet("""
            QTreeView::indicator {
                width: 20px;
                height: 20px;
                margin-left: 6px;
                margin-right: 10px;
            }

            QTreeWidget::item {
                min-height: 60px;
                padding: 0px;
            }

            QTreeWidget::icon {
                margin-left: 4px;
                margin-right: 4px;
            }
        """)

        self.articles_tree.header().setSectionResizeMode(QHeaderView.Interactive)
        self.articles_tree.setSortingEnabled(True)
        self.articles_tree.itemDoubleClicked.connect(self.open_article)
        self.articles_tree.itemClicked.connect(self.toggle_category_expand)

        layout.addLayout(controls_row_top)
        layout.addWidget(self.articles_tree)

        # Set default column widths after widget is added
        self.articles_tree.setColumnWidth(0, 1000) # Title w/ checkbox + icon
        self.articles_tree.setColumnWidth(1, 300) # Source
        self.articles_tree.setColumnWidth(2, 200) # Date

        # Bottom controls
        controls_row_bottom = QHBoxLayout()
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFixedHeight(100)
        layout.addWidget(QLabel("Log Output"))
        layout.addWidget(self.log_output)

        self.send_to_rundown_button = QPushButton("Send to Rundown")
        self.send_to_rundown_button.clicked.connect(self.send_to_rundown)
        controls_row_bottom.addStretch()
        controls_row_bottom.addWidget(self.send_to_rundown_button)

        layout.addLayout(controls_row_bottom)

        self.articles_tab.setLayout(layout)
        self.tabs.addTab(self.articles_tab, "Articles")
        QTimer.singleShot(0, self.set_article_column_widths)

    def set_article_column_widths(self):
        # This is a safe way to set column widths after the widget is visible
        # It needs to be called after the widget has been laid out by Qt
        self.articles_tree.setColumnWidth(0, self.articles_tree.width() * 0.5) # Example: 50% for Headline
        self.articles_tree.setColumnWidth(1, self.articles_tree.width() * 0.25) # Example: 25% for Source
        self.articles_tree.setColumnWidth(2, self.articles_tree.width() * 0.15) # Example: 15% for Date

    def filter_articles(self, index):
        """
        Filters the articles displayed in articles_tree based on the selected category.
        """
        selected_category = self.filter_category_dropdown.currentText()
        self.articles_tree.clear() # Clear existing items

        # For demonstration, let's assume you have a way to access
        # your full list of stories, perhaps stored in self.all_pulled_stories
        # after the PullStoriesWorker finishes.
        # You would iterate through your stories and add only those matching
        # the selected_category to the articles_tree.

        # Example placeholder logic:
        # if hasattr(self, 'all_pulled_stories'):
        #     for category, stories in self.all_pulled_stories.items():
        #         if selected_category == "All" or category == selected_category:
        #             for story_data in stories:
        #                 # Add story_data to articles_tree
        #                 # You'll need to adapt your existing logic for adding items
        #                 # For example:
        #                 item = QTreeWidgetItem([story_data["title"], story_data["source"], story_data["pub_date"]])
        #                 item.setData(0, Qt.UserRole, story_data) # Store full data
        #                 self.articles_tree.addTopLevelItem(item)

        # For now, let's just log a message to show it's working
        self.log_output.append(f"Filtering articles by: {selected_category}")

        # After filtering, you might want to re-expand/collapse categories as needed
        # self.articles_tree.expandAll() or self.articles_tree.collapseAll()
        # and re-apply column widths if they are dynamic.
        self.set_article_column_widths() # Ensure columns are correct after refresh

    def pull_stories(self):
        self.log_output.clear()
        self.log_output.append("Starting to pull stories...")
        current_feeds = self.get_current_feeds()
        story_limit = self.story_limit_slider.value()

        if not current_feeds:
            self.log_output.append("No feeds configured. Please add feeds in the Feed Manager tab.")
            return

        # Disable the pull button while fetching
        self.pull_button.setEnabled(False)
        self.pull_button.setText("Pulling...")

        worker = PullStoriesWorker(current_feeds, story_limit, self.log_output)
        worker.signals.stories_ready.connect(self.display_stories)
        worker.signals.log_message.emit = lambda msg: self.log_output.append(msg) # Redirect worker logs
        worker.signals.get_local_timezone.connect(lambda: self.settings.get("timezone", "America/Chicago"))
        self.threadpool.start(worker)

    def display_stories(self, all_stories):
        self.articles_tree.clear()
        self.all_pulled_stories = all_stories # Store all stories for filtering later

        # Create a mapping for category sorting order
        category_order = {
            "All": 0, "Technology": 1, "Sports": 2, "Politics": 3, "World News": 4,
            "Business": 5, "Entertainment": 6, "Other": 7
        }

        # Sort categories by custom order and then alphabetically for others
        sorted_categories = sorted(all_stories.keys(), key=lambda x: (category_order.get(x, len(category_order)), x))

        for category in sorted_categories:
            stories = all_stories[category]
            if not stories:
                continue

            category_item = QTreeWidgetItem(self.articles_tree, [category, "", ""])
            category_item.setFlags(category_item.flags() & ~Qt.ItemIsSelectable) # Make category not selectable
            category_item.setExpanded(True) # Start expanded

            for story_data in stories:
                item = QTreeWidgetItem(category_item)
                item.setText(0, story_data["title"])
                item.setText(1, story_data["source"])
                item.setText(2, story_data["pub_date"])
                item.setData(0, Qt.UserRole, story_data) # Store full data

                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(0, Qt.Unchecked) # Start unchecked

                # Load and set image
                if story_data.get("image_url"):
                    image_path = self.download_image(story_data["image_url"])
                    if image_path:
                        pixmap = QPixmap(image_path)
                        if not pixmap.isNull():
                            item.setIcon(0, QIcon(pixmap))
                else:
                    # Set a default icon if no image URL is present
                    item.setIcon(0, QIcon(QPixmap("images/default_news_icon.png"))) # Ensure you have a default icon

        self.articles_tree.expandAll()
        self.log_output.append("Stories pulled successfully.")
        self.pull_button.setEnabled(True)
        self.pull_button.setText("Pull Stories")
        self.set_article_column_widths()


    def download_image(self, url):
        try:
            # Create a unique filename based on the URL's hash
            filename = os.path.join(IMAGES_DIR, f"{hash(url)}.png") # Using PNG as a common format
            if os.path.exists(filename):
                return filename # Return cached image if exists

            response = requests.get(url, stream=True, timeout=5)
            response.raise_for_status()

            with open(filename, 'wb') as out_file:
                shutil.copyfileobj(response.raw, out_file)
            del response
            return filename
        except Exception as e:
            # self.log_output.append(f"Error downloading image from {url}: {e}")
            return None # Indicate failure

    def open_article(self, item, column):
        if item.parent(): # Only open if it's a child (actual article)
            story_data = item.data(0, Qt.UserRole)
            if story_data and story_data["link"] and story_data["link"] != '#':
                QDesktopServices.openUrl(QUrl(story_data["link"]))

    def toggle_category_expand(self, item, column):
        # This handles clicks on both category headers and article items
        if not item.parent(): # It's a category header
            item.setExpanded(not item.isExpanded())
            # Collapse other categories if desired (optional)
            # if item.isExpanded():
            #     for i in range(self.articles_tree.topLevelItemCount()):
            #         top_item = self.articles_tree.topLevelItem(i)
            #         if top_item != item and top_item.isExpanded():
            #             top_item.setExpanded(False)

    def send_to_rundown(self):
        selected_stories = []
        for i in range(self.articles_tree.topLevelItemCount()):
            category_item = self.articles_tree.topLevelItem(i)
            for j in range(category_item.childCount()):
                article_item = category_item.child(j)
                if article_item.checkState(0) == Qt.Checked:
                    story_data = article_item.data(0, Qt.UserRole)
                    # Add unique ID if not present
                    if "id" not in story_data:
                        story_data["id"] = str(hash(story_data["link"] + story_data["title"]))
                    selected_stories.append(story_data)

        if not selected_stories:
            QMessageBox.warning(self, "No Selection", "Please select at least one article to send to rundown.")
            return

        current_rundown_items = self.get_rundown_items()
        new_items_added = 0
        for story in selected_stories:
            # Check if item already exists in rundown by link or a unique ID
            exists = False
            for rundown_item in current_rundown_items:
                if rundown_item.get("link") == story.get("link") or rundown_item.get("id") == story.get("id"):
                    exists = True
                    break
            if not exists:
                # Add default values for rundown properties
                story_for_rundown = story.copy() # Don't modify original story_data
                story_for_rundown["duration"] = "00:30" # Default 30 seconds
                story_for_rundown["order"] = len(current_rundown_items) + new_items_added # Sequential order
                story_for_rundown["backtime"] = "" # Will be calculated
                story_for_rundown["active"] = True # Default active
                story_for_rundown["teleprompter_text"] = story_for_rundown["summary"] # Initial teleprompter text
                story_for_rundown["profile"] = "Default Narrator" # Default profile
                story_for_rundown["style"] = "Standard"
                story_for_rundown["tone"] = "Objective"
                story_for_rundown["length"] = "Standard"
                current_rundown_items.append(story_for_rundown)
                new_items_added += 1

        if new_items_added > 0:
            self.update_rundown_tree(current_rundown_items)
            self.calculate_backtimes() # Recalculate after adding
            QMessageBox.information(self, "Sent to Rundown", f"{new_items_added} new articles sent to Rundown tab.")
            self.tabs.setCurrentWidget(self.rundown_tab) # Switch to rundown tab
        else:
            QMessageBox.information(self, "No New Articles", "All selected articles are already in the rundown.")

    def setup_rundown_tab(self):
        self.rundown_tab = QWidget()
        layout = QVBoxLayout(self.rundown_tab)

        # Controls row
        controls_row = QHBoxLayout()
        self.new_rundown_button = QPushButton("New Rundown")
        self.new_rundown_button.clicked.connect(self.new_rundown)
        self.load_rundown_button = QPushButton("Load Rundown")
        self.load_rundown_button.clicked.connect(self.load_rundown)
        self.save_rundown_button = QPushButton("Save Rundown")
        self.save_rundown_button.clicked.connect(self.save_rundown)
        self.save_rundown_as_button = QPushButton("Save Rundown As...")
        self.save_rundown_as_button.clicked.connect(self.save_rundown_as)

        controls_row.addWidget(self.new_rundown_button)
        controls_row.addWidget(self.load_rundown_button)
        controls_row.addWidget(self.save_rundown_button)
        controls_row.addWidget(self.save_rundown_as_button)
        controls_row.addStretch() # Pushes buttons to the left

        # Add rundown clock display
        self.rundown_clock_label = QLabel("Backtime: --:--:--")
        font = self.rundown_clock_label.font()
        font.setPointSize(font.pointSize() + 10) # Make it bigger
        font.setBold(True)
        self.rundown_clock_label.setFont(font)
        self.rundown_clock_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        controls_row.addWidget(self.rundown_clock_label)

        layout.addLayout(controls_row)

        # Rundown Tree setup
        self.rundown_tree = QTreeWidget()
        self.rundown_tree.setColumnCount(6)
        self.rundown_tree.setHeaderLabels(["Title", "Source", "Duration", "Backtime", "Character", "Active"])
        self.rundown_tree.header().setSectionResizeMode(QHeaderView.Interactive)
        self.rundown_tree.setColumnWidth(0, 400) # Title
        self.rundown_tree.setColumnWidth(1, 150) # Source
        self.rundown_tree.setColumnWidth(2, 80)  # Duration
        self.rundown_tree.setColumnWidth(3, 100) # Backtime
        self.rundown_tree.setColumnWidth(4, 150) # Character
        self.rundown_tree.setColumnWidth(5, 60) # Active
        self.rundown_tree.setDragDropMode(QAbstractItemView.InternalMove) # Enable drag-and-drop reordering
        self.rundown_tree.setDropIndicatorShown(True)
        self.rundown_tree.itemChanged.connect(self.handle_rundown_item_changed)
        self.rundown_tree.customContextMenuRequested.connect(self.show_rundown_context_menu)
        self.rundown_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.rundown_tree.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked)

        self.rundown_delegate = RundownItemDelegate(self, self.rundown_tree)
        self.rundown_tree.setItemDelegateForColumn(0, self.rundown_delegate) # For multiline title
        self.rundown_tree.setItemDelegateForColumn(2, self.rundown_delegate) # For duration validation
        self.rundown_tree.setItemDelegateForColumn(3, self.rundown_delegate) # For time editing

        layout.addWidget(self.rundown_tree)

        # Teleprompter and Rewrite section
        teleprompter_rewrite_layout = QHBoxLayout()

        # Teleprompter controls
        teleprompter_layout = QVBoxLayout()
        teleprompter_layout.addWidget(QLabel("<h2>Teleprompter</h2>"))
        # self.teleprompter_text_edit is already initialized in __init__
        teleprompter_layout.addWidget(self.teleprompter_text_edit)

        teleprompter_controls_layout = QHBoxLayout()
        self.select_character_combo = QComboBox()
        self.select_character_combo.setToolTip("Select a character profile for rewriting.")
        self.select_character_combo.currentTextChanged.connect(self.on_character_changed)
        teleprompter_controls_layout.addWidget(QLabel("Character:"))
        teleprompter_controls_layout.addWidget(self.select_character_combo)

        self.apply_to_teleprompter_button = QPushButton("Apply to Teleprompter")
        self.apply_to_teleprompter_button.clicked.connect(self.apply_teleprompter_text)
        teleprompter_controls_layout.addWidget(self.apply_to_teleprompter_button)
        teleprompter_controls_layout.addStretch()
        teleprompter_layout.addLayout(teleprompter_controls_layout)

        teleprompter_rewrite_layout.addLayout(teleprompter_layout)


        # Rewrite controls
        rewrite_options_widget = QWidget()
        rewrite_options_layout = QVBoxLayout(rewrite_options_widget)
        rewrite_options_layout.addWidget(QLabel("<h2>Rewrite Options</h2>"))

        # Style
        style_layout = QHBoxLayout()
        self.style_combo = QComboBox()
        self.style_combo.setToolTip("Select a rewriting style.")
        style_layout.addWidget(QLabel("Style:"))
        style_layout.addWidget(self.style_combo)
        style_layout.addStretch()
        rewrite_options_layout.addLayout(style_layout)

        # Tone
        tone_layout = QHBoxLayout()
        self.tone_combo = QComboBox()
        self.tone_combo.setToolTip("Select a rewriting tone.")
        tone_layout.addWidget(QLabel("Tone:"))
        tone_layout.addWidget(self.tone_combo)
        tone_layout.addStretch()
        rewrite_options_layout.addLayout(tone_layout)

        # Length
        length_layout = QHBoxLayout()
        self.length_combo = QComboBox()
        self.length_combo.setToolTip("Select desired length.")
        length_layout.addWidget(QLabel("Length:"))
        length_layout.addWidget(self.length_combo)
        length_layout.addStretch()
        rewrite_options_layout.addLayout(length_layout)

        self.rewrite_button = QPushButton("Rewrite Selected")
        self.rewrite_button.clicked.connect(self.rewrite_selected_article)
        rewrite_options_layout.addWidget(self.rewrite_button)
        rewrite_options_layout.addStretch() # Pushes content to the top

        teleprompter_rewrite_layout.addWidget(rewrite_options_widget)

        layout.addLayout(teleprompter_rewrite_layout)

        self.tabs.addTab(self.rundown_tab, "Rundown")
        self.load_rundown() # Load default or last rundown
        self.populate_character_dropdown()
        self.populate_rewrite_dropdowns()

        # Timer for backtime calculation
        self.backtime_timer = QTimer(self)
        self.backtime_timer.setInterval(1000) # Update every second
        self.backtime_timer.timeout.connect(self.update_backtime_clock)
        self.backtime_timer.start()

    def new_rundown(self):
        reply = QMessageBox.question(self, "New Rundown",
                                     "Create a new, empty rundown? Any unsaved changes will be lost.",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.update_rundown_tree([])
            self.current_rundown_filename = None
            self.statusBar().showMessage("New rundown created.")
            self.calculate_backtimes() # Recalculate for empty rundown
            self.teleprompter_text_edit.clear()

    def load_rundown(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Load Rundown", "", "Rundown Files (*.json);;All Files (*)")
        if filename:
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    rundown_data = json.load(f)
                self.update_rundown_tree(rundown_data)
                self.current_rundown_filename = filename
                self.statusBar().showMessage(f"Rundown loaded from {os.path.basename(filename)}")
                self.calculate_backtimes()
                self.teleprompter_text_edit.clear()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not load rundown: {e}")

    def save_rundown(self):
        if self.current_rundown_filename:
            self._save_rundown_to_file(self.current_rundown_filename)
        else:
            self.save_rundown_as()

    def save_rundown_as(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Save Rundown As", "", "Rundown Files (*.json);;All Files (*)")
        if filename:
            if not filename.lower().endswith(".json"):
                filename += ".json"
            self._save_rundown_to_file(filename)
            self.current_rundown_filename = filename

    def _save_rundown_to_file(self, filename):
        try:
            rundown_data = self.get_rundown_items()
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(rundown_data, f, indent=4)
            self.statusBar().showMessage(f"Rundown saved to {os.path.basename(filename)}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save rundown: {e}")

    def get_rundown_items(self):
        rundown_items = []
        for i in range(self.rundown_tree.topLevelItemCount()):
            item = self.rundown_tree.topLevelItem(i)
            story_data = item.data(0, Qt.UserRole)
            if story_data: # Ensure it's valid story data
                # Update with current values from the tree
                story_data["duration"] = item.text(2)
                story_data["backtime"] = item.text(3)
                story_data["profile"] = item.text(4)
                story_data["active"] = item.checkState(5) == Qt.Checked
                # Note: "teleprompter_text" needs to be handled via item selection/saving separately
                rundown_items.append(story_data)
        return rundown_items

    def update_rundown_tree(self, rundown_data):
        self.rundown_tree.clear()
        for i, story_data in enumerate(rundown_data):
            item = QTreeWidgetItem(self.rundown_tree)
            item.setText(0, story_data["title"])
            item.setText(1, story_data["source"])
            item.setText(2, story_data.get("duration", "00:00"))
            item.setText(3, story_data.get("backtime", "00:00 AM")) # Placeholder
            item.setText(4, story_data.get("profile", "Default Narrator"))
            item.setCheckState(5, Qt.Checked if story_data.get("active", True) else Qt.Unchecked)
            item.setData(0, Qt.UserRole, story_data) # Store full data

            item.setFlags(item.flags() | Qt.ItemIsEditable | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled)

            # Set a tooltip for the character column
            profile_name = story_data.get("profile", "Default Narrator")
            tooltip = self.profile_tooltips.get(profile_name, "No description available.")
            item.setToolTip(4, tooltip)

        self.rundown_tree.expandAll()
        self.rundown_tree.setColumnWidth(0, self.rundown_tree.width() * 0.4) # Adjust column width dynamically
        self.rundown_tree.setColumnWidth(1, self.rundown_tree.width() * 0.15)
        self.rundown_tree.setColumnWidth(2, self.rundown_tree.width() * 0.1)
        self.rundown_tree.setColumnWidth(3, self.rundown_tree.width() * 0.1)
        self.rundown_tree.setColumnWidth(4, self.rundown_tree.width() * 0.15)
        self.rundown_tree.setColumnWidth(5, self.rundown_tree.width() * 0.05)


    def handle_rundown_item_changed(self, item, column):
        story_data = item.data(0, Qt.UserRole)
        if story_data:
            if column == 2: # Duration changed
                new_duration_str = item.text(2)
                story_data["duration"] = new_duration_str
                self.calculate_backtimes()
            elif column == 4: # Character changed
                new_profile = item.text(4)
                story_data["profile"] = new_profile
                tooltip = self.profile_tooltips.get(new_profile, "No description available.")
                item.setToolTip(4, tooltip) # Update tooltip
            elif column == 5: # Active checkbox changed
                story_data["active"] = item.checkState(5) == Qt.Checked
                self.calculate_backtimes()
            elif column == 0: # Title changed (if edited directly)
                story_data["title"] = item.text(0)

            # Recalculate item height for multiline if column 0 changed
            if column == 0:
                self.rundown_delegate.text_height_cache.clear() # Clear cache for recalculation
                self.rundown_tree.setRowHeight(self.rundown_tree.indexOfTopLevelItem(item), self.rundown_delegate.sizeHint(self.rundown_tree.viewOptions(), item.index()).height())


    def calculate_backtimes(self):
        if self._recalculating_backtimes:
            return # Prevent re-entry

        self._recalculating_backtimes = True
        try:
            total_duration_seconds = 0
            # First pass: calculate total duration of active items
            for i in range(self.rundown_tree.topLevelItemCount()):
                item = self.rundown_tree.topLevelItem(i)
                story_data = item.data(0, Qt.UserRole)
                if story_data and story_data.get("active", True):
                    duration_str = item.text(2)
                    seconds = NewsAggregatorApp.parse_duration_string(duration_str)
                    if seconds is not None:
                        total_duration_seconds += seconds
                    else:
                        self.log_output.append(f"Invalid duration format for '{item.text(0)}': {duration_str}")

            # Get current time for backtime calculation reference
            now = datetime.now()
            # If a backtime has been set for the last item, use that as the show's end time
            last_item_backtime_str = ""
            if self.rundown_tree.topLevelItemCount() > 0:
                last_item = self.rundown_tree.topLevelItem(self.rundown_tree.topLevelItemCount() - 1)
                last_item_backtime_str = last_item.text(3) # Get last item's backtime

            show_end_time = None
            if last_item_backtime_str:
                parsed_time = NewsAggregatorApp.parse_backtime_string(last_item_backtime_str)
                if parsed_time:
                    # Construct datetime for today with the parsed time
                    show_end_time = datetime(now.year, now.month, now.day,
                                             parsed_time.hour, parsed_time.minute, parsed_time.second)
                    # If the parsed time is in the past compared to now, assume it's for tomorrow
                    if show_end_time < now and (now - show_end_time).total_seconds() > 3600: # More than 1 hour difference
                        show_end_time += timedelta(days=1)
                else:
                    self.log_output.append(f"Invalid backtime format for last item: {last_item_backtime_str}")

            if show_end_time is None:
                # Default: Show ends in the near future (e.g., 30 minutes from now, rounded to nearest minute)
                show_end_time = now + timedelta(minutes=30)
                show_end_time = show_end_time.replace(second=0, microsecond=0) # Round to nearest minute

            current_time = show_end_time
            # Second pass: calculate individual backtimes
            for i in range(self.rundown_tree.topLevelItemCount() - 1, -1, -1):
                item = self.rundown_tree.topLevelItem(i)
                story_data = item.data(0, Qt.UserRole)

                duration_seconds = 0
                if story_data and story_data.get("active", True):
                    duration_str = item.text(2)
                    seconds = NewsAggregatorApp.parse_duration_string(duration_str)
                    if seconds is not None:
                        duration_seconds = seconds

                current_time -= timedelta(seconds=duration_seconds)
                item.setText(3, current_time.strftime("%I:%M %p")) # Format as HH:MM AM/PM

            # Update the main rundown clock display
            self.rundown_clock_label.setText(f"Backtime: {current_time.strftime('%I:%M:%S %p')}")

        finally:
            self._recalculating_backtimes = False # Allow re-entry

    def update_backtime_clock(self):
        if self.rundown_tree.topLevelItemCount() > 0:
            first_item = self.rundown_tree.topLevelItem(0)
            first_item_backtime_str = first_item.text(3)
            parsed_time = NewsAggregatorApp.parse_backtime_string(first_item_backtime_str)

            if parsed_time:
                now = datetime.now()
                # Construct datetime for today with the parsed time
                target_datetime = datetime(now.year, now.month, now.day,
                                           parsed_time.hour, parsed_time.minute, parsed_time.second)

                # If the target time is in the past, assume it's for tomorrow
                if target_datetime < now and (now - target_datetime).total_seconds() > 3600: # More than 1 hour difference
                    target_datetime += timedelta(days=1)

                time_remaining = target_datetime - now
                total_seconds = int(time_remaining.total_seconds())

                if total_seconds < 0:
                    display_text = "Show Over"
                else:
                    hours, remainder = divmod(total_seconds, 3600)
                    minutes, seconds = divmod(remainder, 60)
                    display_text = f"Show Starts In: {hours:02}:{minutes:02}:{seconds:02}"
                self.rundown_clock_label.setText(display_text)
            else:
                self.rundown_clock_label.setText("Backtime: --:--:--")
        else:
            self.rundown_clock_label.setText("Backtime: --:--:--") # No items, no backtime

    def show_rundown_context_menu(self, position):
        item = self.rundown_tree.itemAt(position)
        menu = QMenu()

        if item:
            move_up_action = QAction("Move Up", self)
            move_up_action.triggered.connect(lambda: self.move_rundown_item(item, -1))
            menu.addAction(move_up_action)

            move_down_action = QAction("Move Down", self)
            move_down_action.triggered.connect(lambda: self.move_rundown_item(item, 1))
            menu.addAction(move_down_action)

            delete_action = QAction("Delete Item", self)
            delete_action.triggered.connect(lambda: self.delete_rundown_item(item))
            menu.addAction(delete_action)

            # --- Rewrite Options Submenu ---
            rewrite_menu = menu.addMenu("Rewrite Teleprompter Text")

            # Character Profile submenu
            character_menu = rewrite_menu.addMenu("Character Profile")
            for profile_name in self.character_profiles.keys():
                action = QAction(profile_name, self)
                action.setToolTip(self.profile_tooltips.get(profile_name, ""))
                action.triggered.connect(lambda checked, p=profile_name: self.set_item_profile(item, p))
                character_menu.addAction(action)

            # Style submenu
            style_menu = rewrite_menu.addMenu("Style")
            for style_name in self.style_definitions.keys():
                action = QAction(style_name, self)
                action.setToolTip(self.style_definitions.get(style_name, ""))
                action.triggered.connect(lambda checked, s=style_name: self.set_item_rewrite_option(item, "style", s))
                style_menu.addAction(action)

            # Tone submenu
            tone_menu = rewrite_menu.addMenu("Tone")
            for tone_name in self.tone_definitions.keys():
                action = QAction(tone_name, self)
                action.setToolTip(self.tone_definitions.get(tone_name, ""))
                action.triggered.connect(lambda checked, t=tone_name: self.set_item_rewrite_option(item, "tone", t))
                tone_menu.addAction(action)

            # Length submenu
            length_menu = rewrite_menu.addMenu("Length")
            for length_name in self.length_definitions.keys():
                action = QAction(length_name, self)
                action.setToolTip(self.length_definitions.get(length_name, ""))
                action.triggered.connect(lambda checked, l=length_name: self.set_item_rewrite_option(item, "length", l))
                length_menu.addAction(action)

            # Separator for rewrite action
            rewrite_menu.addSeparator()
            rewrite_selected_action = QAction("Generate Rewritten Text", self)
            rewrite_selected_action.triggered.connect(lambda: self.rewrite_selected_article(item))
            rewrite_menu.addAction(rewrite_selected_action)

            # --- Open Original Article ---
            open_original_action = QAction("Open Original Article", self)
            open_original_action.triggered.connect(lambda: self.open_article(item, 0)) # Re-use open_article
            menu.addAction(open_original_action)

        menu.exec(self.rundown_tree.mapToGlobal(position))

    def set_item_profile(self, item, profile_name):
        story_data = item.data(0, Qt.UserRole)
        if story_data:
            story_data["profile"] = profile_name
            item.setText(4, profile_name) # Update displayed character
            tooltip = self.profile_tooltips.get(profile_name, "No description available.")
            item.setToolTip(4, tooltip) # Update tooltip

    def set_item_rewrite_option(self, item, option_type, option_name):
        story_data = item.data(0, Qt.UserRole)
        if story_data:
            story_data[option_type] = option_name
            # Optionally update UI if you decide to display these settings directly in the tree

    def move_rundown_item(self, item, direction):
        current_row = self.rundown_tree.indexOfTopLevelItem(item)
        new_row = current_row + direction

        if 0 <= new_row < self.rundown_tree.topLevelItemCount():
            # Get data for selected item
            item_data = item.data(0, Qt.UserRole)
            # Remove item from current position
            self.rundown_tree.takeTopLevelItem(current_row)

            # Insert item at new position
            new_item = QTreeWidgetItem()
            new_item.setText(0, item_data["title"])
            new_item.setText(1, item_data["source"])
            new_item.setText(2, item_data["duration"])
            new_item.setText(3, item_data["backtime"])
            new_item.setText(4, item_data["profile"])
            new_item.setCheckState(5, Qt.Checked if item_data["active"] else Qt.Unchecked)
            new_item.setData(0, Qt.UserRole, item_data)
            new_item.setFlags(item.flags() | Qt.ItemIsEditable | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled) # Retain flags
            new_item.setToolTip(4, self.profile_tooltips.get(item_data["profile"], "No description available.")) # Re-add tooltip

            self.rundown_tree.insertTopLevelItem(new_row, new_item)
            self.rundown_tree.setCurrentItem(new_item) # Select the moved item
            self.calculate_backtimes() # Recalculate backtimes after reordering

    def delete_rundown_item(self, item):
        reply = QMessageBox.question(self, "Delete Rundown Item",
                                     f"Are you sure you want to delete '{item.text(0)}' from the rundown?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            root = self.rundown_tree.invisibleRootItem()
            root.removeChild(item)
            self.calculate_backtimes() # Recalculate backtimes after deletion
            self.teleprompter_text_edit.clear() # Clear teleprompter if deleted item was selected

    def on_tab_changed(self, index):
        if self.tabs.widget(index) == self.rundown_tab:
            self.calculate_backtimes() # Recalculate when rundown tab is shown

    def populate_character_dropdown(self):
        self.select_character_combo.clear()
        for name in self.character_profiles.keys():
            self.select_character_combo.addItem(name)
            # Add tooltip for each item in the combo box
            self.select_character_combo.setItemData(
                self.select_character_combo.findText(name),
                self.profile_tooltips.get(name, ""),
                Qt.ToolTipRole
            )
        # Select the profile of the currently selected rundown item if available
        current_item = self.rundown_tree.currentItem()
        if current_item:
            story_data = current_item.data(0, Qt.UserRole)
            if story_data and "profile" in story_data:
                self.select_character_combo.setCurrentText(story_data["profile"])


    def on_character_changed(self, profile_name):
        current_item = self.rundown_tree.currentItem()
        if current_item:
            story_data = current_item.data(0, Qt.UserRole)
            if story_data:
                story_data["profile"] = profile_name
                # self.update_rundown_tree_item(current_item, story_data) # Update tree item if needed

    def populate_rewrite_dropdowns(self):
        self.style_combo.clear()
        for name, desc in self.style_definitions.items():
            self.style_combo.addItem(name)
            self.style_combo.setItemData(self.style_combo.findText(name), desc, Qt.ToolTipRole)

        self.tone_combo.clear()
        for name, desc in self.tone_definitions.items():
            self.tone_combo.addItem(name)
            self.tone_combo.setItemData(self.tone_combo.findText(name), desc, Qt.ToolTipRole)

        self.length_combo.clear()
        for name, desc in self.length_definitions.items():
            self.length_combo.addItem(name)
            self.length_combo.setItemData(self.length_combo.findText(name), desc, Qt.ToolTipRole)

        # Connect signals
        self.style_combo.currentTextChanged.connect(lambda text: self.update_selected_item_rewrite_option("style", text))
        self.tone_combo.currentTextChanged.connect(lambda text: self.update_selected_item_rewrite_option("tone", text))
        self.length_combo.currentTextChanged.connect(lambda text: self.update_selected_item_rewrite_option("length", text))

        # Update dropdowns based on currently selected item in rundown_tree
        self.on_rundown_item_selected(self.rundown_tree.currentItem(), None)


    def update_selected_item_rewrite_option(self, option_type, option_name):
        current_item = self.rundown_tree.currentItem()
        if current_item:
            story_data = current_item.data(0, Qt.UserRole)
            if story_data:
                story_data[option_type] = option_name
                # self.update_rundown_tree_item(current_item, story_data) # If you want to update tree display

    def rewrite_selected_article(self, item=None):
        if not item: # Called from button, get current selection
            item = self.rundown_tree.currentItem()

        if not item:
            QMessageBox.warning(self, "No Article Selected", "Please select an article in the rundown to rewrite.")
            return

        story_data = item.data(0, Qt.UserRole)
        if not story_data:
            QMessageBox.warning(self, "Error", "Selected item has no story data.")
            return

        original_summary = story_data.get("original_summary", story_data.get("summary", "No summary available."))
        selected_profile_name = story_data.get("profile", self.select_character_combo.currentText())
        selected_style_name = story_data.get("style", self.style_combo.currentText())
        selected_tone_name = story_data.get("tone", self.tone_combo.currentText())
        selected_length_name = story_data.get("length", self.length_combo.currentText())

        profile_prompt = self.character_profiles.get(selected_profile_name, {}).get("prompt", "You are an objective news narrator.")
        style_prompt = self.style_definitions.get(selected_style_name, "")
        tone_prompt = self.tone_definitions.get(selected_tone_name, "")
        length_prompt = self.length_definitions.get(selected_length_name, "")

        # Construct a combined prompt for the AI (replace with actual AI call)
        ai_prompt = (
            f"{profile_prompt} {style_prompt} {tone_prompt} {length_prompt}\n"
            f"Rewrite the following news summary: {original_summary}"
        ).strip()

        # Simulate AI rewriting (replace with actual API call)
        self.log_output.append(f"Rewriting for '{story_data['title']}' with profile '{selected_profile_name}'...")
        self.log_output.append(f"AI Prompt (simulated): {ai_prompt[:100]}...") # Show a snippet of the prompt
        # In a real application, you would make an API call here
        rewritten_text = f"[[Rewritten by AI for {selected_profile_name} in {selected_style_name}, {selected_tone_name}, {selected_length_name} style]]\n\n" + original_summary # Placeholder

        story_data["teleprompter_text"] = rewritten_text
        story_data["rewritten"] = True
        self.teleprompter_text_edit.setText(rewritten_text)
        self.log_output.append(f"Rewriting for '{story_data['title']}' complete.")

    def on_rundown_item_selected(self, current, previous):
        if current:
            story_data = current.data(0, Qt.UserRole)
            if story_data:
                self.teleprompter_text_edit.setText(story_data.get("teleprompter_text", story_data.get("summary", "")))

                # Update character dropdown
                profile = story_data.get("profile")
                if profile and profile in self.character_profiles:
                    self.select_character_combo.setCurrentText(profile)

                # Update rewrite options dropdowns
                self.style_combo.setCurrentText(story_data.get("style", "Standard"))
                self.tone_combo.setCurrentText(story_data.get("tone", "Objective"))
                self.length_combo.setCurrentText(story_data.get("length", "Standard"))

        else:
            self.teleprompter_text_edit.clear()
            self.select_character_combo.setCurrentIndex(0) # Default to first item
            self.style_combo.setCurrentIndex(0)
            self.tone_combo.setCurrentIndex(0)
            self.length_combo.setCurrentIndex(0)

    def apply_teleprompter_text(self):
        current_item = self.rundown_tree.currentItem()
        if current_item:
            story_data = current_item.data(0, Qt.UserRole)
            if story_data:
                story_data["teleprompter_text"] = self.teleprompter_text_edit.toPlainText()
                QMessageBox.information(self, "Text Applied", "Teleprompter text updated for selected article.")
        else:
            QMessageBox.warning(self, "No Article Selected", "Please select an article in the rundown to apply text to.")

    @staticmethod
    def parse_duration_string(duration_str):
        """Parse HH:MM or MM:SS duration string into total seconds."""
        if not isinstance(duration_str, str):
            return None
        parts = list(map(int, duration_str.split(':')))
        try:
            if len(parts) == 2:
                minutes, seconds = parts
                if 0 <= seconds < 60:
                    return minutes * 60 + seconds
            elif len(parts) == 3:
                hours, minutes, seconds = parts
                if 0 <= minutes < 60 and 0 <= seconds < 60:
                    return hours * 3600 + minutes * 60 + seconds
            return None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def parse_backtime_string(bt_str):
        """Try multiple time formats and return a datetime.time object or None."""
        if not bt_str or not bt_str.strip():
            return None

        formats = ("%I:%M:%S %p", "%I:%M %p", "%H:%M:%S", "%H:%M")
        for fmt in formats:
            try:
                return datetime.strptime(bt_str.strip(), fmt).time()
            except ValueError:
                continue
        return None

def launch_app():
    import os
    os.environ["QT_SCALE_FACTOR_ROUNDING_POLICY"] = "PassThrough"

    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt

    # Removed: QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True) - Handled by QGuiApplication.setHighDpiScaleFactorRoundingPolicy earlier

    QApplication.setStyle("Fusion")
    app = QApplication(sys.argv)
    app.setStyleSheet("""
        QTreeView::indicator {
            width: 32px;
            height: 32px;
        }
        QTreeWidget::item {
            min-height: 80px; /* Adjust based on icon size and desired spacing */
        }
    """)

    main_window = NewsAggregatorApp()
    main_window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    launch_app()