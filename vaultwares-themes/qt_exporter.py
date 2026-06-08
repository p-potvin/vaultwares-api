import sys
import os

# Ensure theme_manager is importable
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from theme_manager import VaultThemeManager, VaultTheme


class QtThemeExporter:
    def __init__(self):
        self.manager = VaultThemeManager()

    def get_all_themes(self):
        return self.manager.get_themes()

    def get_theme_by_name(self, name: str):
        return self.manager.get_theme_by_name(name)

    def generate_qss(self, theme: VaultTheme) -> str:
        """
        Generates a PySide6 QSS stylesheet for the given VaultTheme.

        Applies all semantic color tokens (error, warning, success, info, muted)
        and uses a layered surface hierarchy for depth and visual clarity.
        """
        t = theme  # alias

        self.stylesheet = f"""
            /* ── Base ─────────────────────────────────────────── */
            QMainWindow, QDialog, QWidget {{
                background-color: {t.background};
                color: {t.text};
                font-family: 'Segoe UI', 'Inter', system-ui;
                font-size: 12px;
            }}

            QSplitter::handle {{
                background-color: transparent;
            }}
            QSplitter::handle:horizontal {{
                width: 4px;
            }}
            QSplitter::handle:vertical {{
                height: 4px;
            }}

            QScrollArea, QScrollArea > QWidget {{
                background-color: transparent;
                border: none;
            }}

            /* ── Labels ───────────────────────────────────────── */
            QLabel {{
                color: {t.text};
                background: transparent;
            }}


            QLabel#SectionTitleConfig, QLabel#SectionTitleMonitor {{
                color: {t.accent};
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 2.5px;
                text-transform: uppercase;
                padding-bottom: 4px;
                border-bottom: 1px solid {t.border};
            }}

            QLabel#FooterLabel {{
                color: {t.muted};
                font-size: 9px;
                letter-spacing: 2px;
            }}

            QLabel#LogoLabel {{
                background-color: transparent;
            }}

            QLabel#StatusLabel {{
                color: {t.text_muted};
                font-size: 11px;
                font-style: italic;
                min-height: 16px;
            }}

            QLabel#TagBadge {{
                background-color: {t.accent};
                color: {t.text_inverse};
                border-radius: 4px;
                padding: 1px 6px;
                font-size: 10px;
                font-weight: 600;
            }}

            /* ── Inputs ───────────────────────────────────────── */
            QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 3px;
                padding: 2px 4px;
                min-height: 22px;
                color: {t.text};
                selection-background-color: {t.accent};
                selection-color: {t.text_inverse};
            }}

            QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
                border: 1.5px solid {t.accent};
                background-color: {t.surface_alt};
            }}

            QLineEdit:disabled, QTextEdit:disabled, QSpinBox:disabled {{
                color: {t.muted};
                border-color: {t.border};
                background-color: {t.surface};
            }}

            QLineEdit::placeholder {{
                color: {t.muted};
            }}

            /* ── ComboBox ─────────────────────────────────────── */
            QComboBox {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 3px;
                padding: 2px 4px;
                min-height: 22px;
                color: {t.text};
            }}

            QComboBox:focus, QComboBox:on {{
                border: 1.5px solid {t.accent};
            }}

            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}

            QComboBox::down-arrow {{
                width: 10px;
                height: 10px;
            }}

            QComboBox QAbstractItemView {{
                background-color: {t.surface_alt};
                border: 1px solid {t.border};
                border-radius: 3px;
                selection-background-color: {t.accent};
                selection-color: {t.text_inverse};
                padding: 4px;
                color: {t.text};
            }}

            /* ── Buttons ──────────────────────────────────────── */
            QPushButton {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 4px;
                padding: 7px 16px;
                color: {t.text};
                font-weight: 500;
                min-height: 30px;
            }}

            QPushButton:hover {{
                background-color: {t.surface_alt};
                border-color: {t.accent_muted};
            }}

            QPushButton:pressed {{
                background-color: {t.accent_muted};
                color: {t.text_inverse};
            }}

            QPushButton:disabled {{
                color: {t.muted};
                border-color: {t.border};
                background-color: {t.surface};
            }}

            QPushButton#PrimaryBtn {{
                background-color: {t.accent};
                color: {t.text_inverse};
                font-weight: 700;
                font-size: 13px;
                letter-spacing: 1px;
                border: none;
                border-radius: 4px;
            }}

            QPushButton#PrimaryBtn:hover {{
                background-color: {t.accent_muted};
            }}

            QPushButton#PrimaryBtn:disabled {{
                background-color: {t.muted};
                color: {t.surface};
            }}

            QPushButton#DangerBtn {{
                background-color: {t.error_bg};
                border: 1px solid {t.error};
                color: {t.error};
            }}

            QPushButton#DangerBtn:hover {{
                background-color: {t.error};
                color: {t.text_inverse};
            }}

            QPushButton#SecondaryBtn {{
                background-color: transparent;
                border: 1px solid {t.border};
                border-radius: 4px;
                color: {t.text_muted};
                padding: 2px 6px;
                min-height: 20px;
            }}

            QPushButton#SecondaryBtn:hover {{
                background-color: {t.surface_elevated};
                border-color: {t.accent_muted};
                color: {t.text};
            }}

            /* ── CheckBox ─────────────────────────────────────── */
            QCheckBox {{
                color: {t.text};
                spacing: 8px;
                min-height: 20px;
            }}

            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 1.5px solid {t.border};
                border-radius: 4px;
                background-color: {t.surface};
            }}

            QCheckBox::indicator:hover {{
                border-color: {t.accent_muted};
            }}

            QCheckBox::indicator:checked {{
                background-color: {t.accent};
                border-color: {t.accent};
                image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' width='16' height='16'><path d='M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z' fill='{t.text_inverse.replace('#', '%23')}'/></svg>");
            }}

            QCheckBox:disabled {{
                color: {t.muted};
            }}

            /* ── Panels / Frames ──────────────────────────────── */
            QFrame#ConfigPanel {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 14px;
            }}

            QFrame#MonitorPanel {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 14px;
            }}

            QFrame#Separator {{
                background-color: {t.border};
                max-height: 1px;
                border: none;
            }}

            /* Status banner frames */
            QFrame#ErrorBanner {{
                background-color: {t.error_bg};
                border: 1px solid {t.error};
                border-radius: 4px;
                padding: 4px;
            }}

            QFrame#WarningBanner {{
                background-color: {t.warning_bg};
                border: 1px solid {t.warning};
                border-radius: 4px;
                padding: 4px;
            }}

            QFrame#SuccessBanner {{
                background-color: {t.success_bg};
                border: 1px solid {t.success};
                border-radius: 4px;
                padding: 4px;
            }}

            QFrame#InfoBanner {{
                background-color: {t.info_bg};
                border: 1px solid {t.info};
                border-radius: 4px;
                padding: 4px;
            }}

            /* ── Progress Bar ─────────────────────────────────── */
            QProgressBar {{
                background-color: {t.surface_alt};
                border: none;
                border-radius: 4px;
                text-align: center;
                color: {t.text};
                font-size: 10px;
                font-weight: 600;
            }}

            QProgressBar::chunk {{
                background-color: {t.accent};
                border-radius: 4px;
            }}

            /* ── Log Area ─────────────────────────────────────── */
            QTextEdit#LogArea {{
                background-color: {t.primary};
                border: none;
                border-radius: 6px;
                color: {t.text};
                font-family: 'Cascadia Code', 'Consolas', 'Courier New', monospace;
                font-size: 11px;
                line-height: 1.5;
                padding: 4px;
            }}

            /* ── ScrollBar ────────────────────────────────────── */
            QScrollBar:vertical {{
                background: {t.surface};
                width: 8px;
                border-radius: 4px;
            }}

            QScrollBar::handle:vertical {{
                background: {t.border};
                border-radius: 4px;
                min-height: 20px;
            }}

            QScrollBar::handle:vertical:hover {{
                background: {t.accent_muted};
            }}

            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}

            QScrollBar:horizontal {{
                background: {t.surface};
                height: 8px;
                border-radius: 4px;
            }}

            QScrollBar::handle:horizontal {{
                background: {t.border};
                border-radius: 4px;
                min-width: 20px;
            }}

            QScrollBar::handle:horizontal:hover {{
                background: {t.accent_muted};
            }}

            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}

            /* ── ToolTips ─────────────────────────────────────── */
            QToolTip {{
                background-color: {t.surface_alt};
                color: {t.text};
                border: 1px solid {t.border};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }}

            /* ── Semantic Text Roles (for use in rich-text HTML) ─ */
            /* Use inline style="color: ..." in log messages, e.g.: */
            /* f"<span style='color: {{theme.error}}'>error message</span>" */
        """
