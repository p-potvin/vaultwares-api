import pytest
import os
import sys
import importlib.util

# Ensure the parent directory is in sys.path so the module can resolve properly
sys.path.insert(0, os.path.join(os.getcwd(), "vault-themes"))

# Robustly load the module from the hyphenated directory
module_name = "theme_manager"
file_path = os.path.join(os.getcwd(), "vault-themes", "theme_manager.py")
spec = importlib.util.spec_from_file_location(module_name, file_path)
theme_manager_mod = importlib.util.module_from_spec(spec)
sys.modules[module_name] = theme_manager_mod
spec.loader.exec_module(theme_manager_mod)

VaultThemeManager = theme_manager_mod.VaultThemeManager
VaultTheme = theme_manager_mod.VaultTheme

class TestVaultThemeManager:
    @pytest.fixture
    def manager(self):
        return VaultThemeManager()

    def test_get_themes(self, manager):
        themes = manager.get_themes()
        assert len(themes) == 10
        assert isinstance(themes[0], VaultTheme)

    def test_get_theme_by_index(self, manager):
        theme = manager.get_theme(0)
        assert theme.name == "Golden Slate"

    def test_get_glass_rgba(self, manager):
        rgba = manager.get_glass_rgba("#FFFFFF", 128)
        assert rgba == "rgba(255, 255, 255, 0.5019607843137255)"
