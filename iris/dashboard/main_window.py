"""Main PySide6 dashboard window for IRIS Sprint 1."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from iris.core.iris_core import IrisCore


class MainWindow(QMainWindow):
    """Simple Sprint 1 dashboard shell with no business logic."""

    def __init__(self, core: IrisCore) -> None:
        super().__init__()
        self._core = core

        self.setWindowTitle("IRIS Synapse Labs")
        self.setMinimumSize(420, 260)
        self._build_ui()

    def _build_ui(self) -> None:
        """Create and arrange dashboard widgets."""
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(14)

        title_label = QLabel("IRIS", container)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setObjectName("titleLabel")

        company_label = QLabel("Synapse Labs", container)
        company_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        status = self._core.get_status()
        status_label = QLabel(f"IRIS Status: {status.status.value}", container)
        status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        agents_label = QLabel(
            f"Registered Agents: {status.registered_agents}",
            container,
        )
        agents_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        start_button = QPushButton("Start", container)
        stop_button = QPushButton("Stop", container)
        settings_button = QPushButton("Settings", container)

        layout.addWidget(title_label)
        layout.addWidget(company_label)
        layout.addSpacing(12)
        layout.addWidget(status_label)
        layout.addWidget(agents_label)
        layout.addSpacing(12)
        layout.addWidget(start_button)
        layout.addWidget(stop_button)
        layout.addWidget(settings_button)

        container.setLayout(layout)
        self.setCentralWidget(container)
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #f7f8fa;
            }

            QLabel {
                color: #202124;
                font-size: 16px;
            }

            QLabel#titleLabel {
                font-size: 32px;
                font-weight: 700;
            }

            QPushButton {
                min-width: 160px;
                min-height: 34px;
                border: 1px solid #b8c0cc;
                border-radius: 6px;
                background-color: #ffffff;
                color: #202124;
                font-size: 14px;
            }

            QPushButton:hover {
                background-color: #edf2f7;
            }
            """
        )
