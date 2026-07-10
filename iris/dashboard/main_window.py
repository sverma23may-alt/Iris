"""Main PySide6 dashboard window for IRIS."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from iris.dashboard.view_model import DashboardState, DashboardViewModel


class MainWindow(QMainWindow):
    """IRIS dashboard shell backed by a presentation model."""

    def __init__(self, view_model: DashboardViewModel) -> None:
        super().__init__()
        self._view_model = view_model
        self._metric_labels: dict[str, QLabel] = {}
        self._status_labels: dict[str, QLabel] = {}
        self._log_panel: QTextEdit | None = None

        self.setWindowTitle("IRIS Synapse Labs")
        self.setMinimumSize(980, 640)
        self._build_ui()
        self._configure_refresh()
        self._refresh()

    def _build_ui(self) -> None:
        """Create and arrange dashboard widgets."""
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(18)

        header = self._build_header(container)
        metrics = self._build_metrics(container)
        actions = self._build_actions(container)
        logs = self._build_logs(container)

        layout.addLayout(header)
        layout.addLayout(metrics)
        layout.addLayout(actions)
        layout.addWidget(logs, stretch=1)

        container.setLayout(layout)
        self.setCentralWidget(container)
        self._build_status_bar()
        self._apply_styles()

    def _build_header(self, parent: QWidget) -> QHBoxLayout:
        layout = QHBoxLayout()

        title_group = QVBoxLayout()
        title = QLabel("IRIS", parent)
        title.setObjectName("titleLabel")
        subtitle = QLabel("Synapse Labs", parent)
        subtitle.setObjectName("subtitleLabel")
        title_group.addWidget(title)
        title_group.addWidget(subtitle)

        status = QLabel(parent)
        status.setObjectName("statusPill")
        status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._metric_labels["iris_status"] = status

        layout.addLayout(title_group)
        layout.addStretch(1)
        layout.addWidget(status)
        return layout

    def _build_metrics(self, parent: QWidget) -> QGridLayout:
        layout = QGridLayout()
        layout.setHorizontalSpacing(14)
        layout.setVerticalSpacing(14)

        cards = [
            ("cpu", "CPU Usage"),
            ("ram", "RAM Usage"),
            ("current_time", "Current Time"),
            ("queue_size", "Queue Size"),
            ("running_tasks", "Running Tasks"),
            ("completed_tasks", "Completed Tasks"),
            ("registered_agents", "Registered Agents"),
        ]

        for index, (key, title) in enumerate(cards):
            card = self._metric_card(parent, key, title)
            layout.addWidget(card, index // 4, index % 4)

        return layout

    def _metric_card(self, parent: QWidget, key: str, title: str) -> QWidget:
        card = QWidget(parent)
        card.setObjectName("metricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        title_label = QLabel(title, card)
        title_label.setObjectName("metricTitle")

        value_label = QLabel("--", card)
        value_label.setObjectName("metricValue")
        self._metric_labels[key] = value_label

        layout.addWidget(title_label)
        layout.addWidget(value_label)
        return card

    def _build_actions(self, parent: QWidget) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(10)

        start_button = QPushButton("Start", parent)
        stop_button = QPushButton("Stop", parent)
        settings_button = QPushButton("Settings", parent)

        layout.addWidget(start_button)
        layout.addWidget(stop_button)
        layout.addWidget(settings_button)
        layout.addStretch(1)
        return layout

    def _build_logs(self, parent: QWidget) -> QWidget:
        section = QWidget(parent)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        label = QLabel("Logs", section)
        label.setObjectName("sectionLabel")

        self._log_panel = QTextEdit(section)
        self._log_panel.setObjectName("logPanel")
        self._log_panel.setReadOnly(True)

        layout.addWidget(label)
        layout.addWidget(self._log_panel)
        return section

    def _build_status_bar(self) -> None:
        status_bar = QStatusBar(self)
        self.setStatusBar(status_bar)

        for key in ("cpu", "ram", "python_version", "current_time", "iris_version"):
            label = QLabel(self)
            label.setObjectName("statusBarLabel")
            self._status_labels[key] = label
            status_bar.addPermanentWidget(label)

    def _configure_refresh(self) -> None:
        timer = QTimer(self)
        timer.timeout.connect(self._refresh)
        timer.start(1000)

    def _refresh(self) -> None:
        state = self._view_model.snapshot()
        self._render_state(state)

    def _render_state(self, state: DashboardState) -> None:
        metrics = state.metrics
        values = {
            "iris_status": f"IRIS Status: {state.iris_status}",
            "cpu": f"{metrics.cpu_percent:.1f}%",
            "ram": f"{metrics.ram_percent:.1f}%",
            "current_time": metrics.current_time,
            "queue_size": str(state.queue_size),
            "running_tasks": str(state.running_tasks),
            "completed_tasks": str(state.completed_tasks),
            "registered_agents": str(state.registered_agents),
        }

        for key, value in values.items():
            self._metric_labels[key].setText(value)

        self._status_labels["cpu"].setText(f"CPU {metrics.cpu_percent:.1f}%")
        self._status_labels["ram"].setText(f"RAM {metrics.ram_percent:.1f}%")
        self._status_labels["python_version"].setText(f"Python {metrics.python_version}")
        self._status_labels["current_time"].setText(metrics.current_time)
        self._status_labels["iris_version"].setText(f"IRIS {metrics.iris_version}")

        if self._log_panel is not None:
            self._log_panel.setPlainText("\n".join(state.logs[-200:]))
            self._log_panel.verticalScrollBar().setValue(
                self._log_panel.verticalScrollBar().maximum()
            )

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #f5f7fb;
            }

            QLabel {
                color: #202124;
                font-size: 14px;
            }

            QLabel#titleLabel {
                font-size: 34px;
                font-weight: 700;
            }

            QLabel#subtitleLabel {
                color: #5f6b7a;
                font-size: 15px;
            }

            QLabel#statusPill {
                min-width: 150px;
                padding: 8px 12px;
                border: 1px solid #b7d7c0;
                border-radius: 6px;
                background-color: #e8f6ed;
                color: #14532d;
                font-weight: 600;
            }

            QLabel#sectionLabel {
                color: #2d3748;
                font-size: 16px;
                font-weight: 600;
            }

            QWidget#metricCard {
                background-color: #ffffff;
                border: 1px solid #d8dee8;
                border-radius: 8px;
            }

            QLabel#metricTitle {
                color: #64748b;
                font-size: 13px;
            }

            QLabel#metricValue {
                color: #111827;
                font-size: 24px;
                font-weight: 700;
            }

            QPushButton {
                min-width: 110px;
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

            QTextEdit#logPanel {
                background-color: #101418;
                border: 1px solid #2a3441;
                border-radius: 8px;
                color: #d7e1ea;
                font-family: Consolas, monospace;
                font-size: 12px;
                padding: 10px;
            }

            QStatusBar {
                background-color: #ffffff;
                border-top: 1px solid #d8dee8;
            }

            QLabel#statusBarLabel {
                color: #475569;
                padding: 0 8px;
            }
            """
        )
