"""
VaultWares UI Layout Auditor (PySide6)
======================================
This tool replaces unreliable vision-model/screenshot-based UI testing with strict,
deterministic mathematical geometry checks.

Why use this? 
AI vision models frequently hallucinate positive results and fail to spot overlapping
borders, clipped text, or squished QSplitters. This programmatic auditor walks 
a QWidget tree and calculates the physical intersections and bounds.

Usage with `pytest-qt`:
-----------------------
1. Copy this auditor file into your project's `tests/utils/` directory.
2. Inside your pytest tests, intentionally agitate the UI (e.g. shrinking form factors, 
   hiding panels, expanding text).
3. Wait for the Qt Event Loop to resolve (`qtbot.wait(100)`).
4. Pass the root widget to `audit_widget_tree()`. 

Example Test Template:
----------------------
```python
import pytest
from my_app.gui import MainWindow
from tests.utils.layout_auditor import audit_widget_tree

def test_app_responsive_layout(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    
    # 1. Agitate the layout (e.g., shrink to minimum bounds)
    window.resize(600, 400)
    
    # 2. Hide a major layout component to force redistribution
    window.left_panel.hide()
    
    # Wait for the layout engine to recalculate geometry
    qtbot.wait(200)
    
    # 3. Mathematically audit the bounds
    errors = audit_widget_tree(window)
    
    if errors:
        pytest.fail(f"Layout warped or clipped!\\n" + "\\n".join(errors))
```
"""

from PySide6.QtWidgets import QWidget
from typing import List, Set

def audit_widget_tree(root_widget: QWidget) -> Set[str]:
    """
    Recursively walks a PySide6 widget tree and returns a detailed set of layout errors.
    Checks for:
    - Text clipping (widget height < fontMetrics bounding rect height)
    - Orphan bounds / Overflows (child widget extends outside its parent container)
    """
    errors = []
    
    def walk(widget: QWidget, level: int = 0):
        if not widget.isVisible():
            return
        
        # Check text clipping
        if hasattr(widget, "text") and callable(widget.text):
            text = widget.text()
            if text:
                fm = widget.fontMetrics()
                # Use boundingRect to get the actual text height, accounting for word wrap if enabled
                rect = fm.boundingRect(0, 0, widget.width(), 2000, 0, text)
                
                # Allow a 1px tolerance for font-rendering antialiasing artifacts
                if rect.height() > widget.height() + 1:
                    errors.append(f"Text Clipped: '{text[:20]}...' in {widget.__class__.__name__}. "
                                  f"Text height: {rect.height()}, Widget height: {widget.height()}")

        # Check for children overflowing parent boundaries
        for child in widget.children():
            if isinstance(child, QWidget) and child.isVisible():
                if child.isWindow():
                    continue  # Tooltips, dialogs, sub-windows
                
                child_geom = child.geometry()
                parent_geom = widget.rect()  # Parent's internal geometry (0, 0, width, height)
                
                if not parent_geom.contains(child_geom):
                    # Minor overflows (1-5px) might be anti-aliasing, layout margins, or focus rings.
                    # Significant ones mean the widget layout has collapsed or squished
                    if child_geom.right() > parent_geom.right() + 5 or child_geom.bottom() > parent_geom.bottom() + 5:
                        errors.append(f"Overflow: {child.__class__.__name__} bounds ({child_geom.x()}, {child_geom.y()}, {child_geom.width()}x{child_geom.height()}) "
                                      f"exceed parent {widget.__class__.__name__} bounds ({parent_geom.width()}x{parent_geom.height()})")
                walk(child, level + 1)
                
    walk(root_widget)
    # Deduplicate errors, returning a clean set
    return set(errors)
