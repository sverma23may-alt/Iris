"""IRIS Vision command-center UI."""

from __future__ import annotations

import math
import time
from collections import deque
from getpass import getuser
from html import escape
from typing import Any

try:  # pragma: no cover - optional UI dependency
    import pyqtgraph as pg
except ImportError:  # pragma: no cover
    pg = None

from PySide6.QtCore import QEasingCurve, QObject, QPointF, QPropertyAnimation, QRectF, QSize, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGraphicsBlurEffect,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSlider,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from iris.vision.view_model import ChatMessage, ChatResult, DashboardState, DashboardViewModel


class MainWindow(QMainWindow):
    """Premium AI operating system shell backed by the existing IRIS backend."""

    PAGES = (
        ("mission", "Mission Control", QStyle.StandardPixmap.SP_ComputerIcon),
        ("chat", "IRIS Chat", QStyle.StandardPixmap.SP_MessageBoxQuestion),
        ("research", "Research", QStyle.StandardPixmap.SP_FileDialogContentsView),
        ("studio", "Studio", QStyle.StandardPixmap.SP_MediaPlay),
        ("router", "AI Router", QStyle.StandardPixmap.SP_DriveNetIcon),
        ("workflow", "Workflow", QStyle.StandardPixmap.SP_ArrowDown),
        ("scheduler", "Scheduler", QStyle.StandardPixmap.SP_FileDialogDetailedView),
        ("analytics", "Analytics", QStyle.StandardPixmap.SP_FileDialogInfoView),
        ("telegram", "Telegram", QStyle.StandardPixmap.SP_MessageBoxInformation),
        ("voice", "Voice", QStyle.StandardPixmap.SP_MediaVolume),
        ("settings", "Settings", QStyle.StandardPixmap.SP_FileDialogListView),
    )

    def __init__(self, view_model: DashboardViewModel) -> None:
        super().__init__()
        self._view_model = view_model
        self._page_buttons: dict[str, QToolButton] = {}
        self._pages: dict[str, QWidget] = {}
        self._metric_labels: dict[str, QLabel] = {}
        self._status_labels: dict[str, QLabel] = {}
        self._charts: dict[str, LiveChart] = {}
        self._panels: dict[str, QTextEdit] = {}
        self._providers: list[OrbitCard] = []
        self._focus_widgets: list[QWidget] = []
        self._sidebar: QFrame | None = None
        self._stage: QFrame | None = None
        self._top_bar: QFrame | None = None
        self._notification_panel: QFrame | None = None
        self._notification_badge: QLabel | None = None
        self._notification_text: QTextEdit | None = None
        self._notification_search: QLineEdit | None = None
        self._notification_filter: QLineEdit | None = None
        self._workflow_graph: WorkflowGraph | None = None
        self._background: NeuralBackground | None = None
        self._core: IrisCoreWidget | None = None
        self._voice_core: IrisCoreWidget | None = None
        self._voice_waveform: "VoiceWaveform | None" = None
        self._voice_input: QLineEdit | None = None
        self._voice_history: QTextEdit | None = None
        self._voice_provider: QComboBox | None = None
        self._voice_mic_status: QLabel | None = None
        self._chat_core: IrisCoreWidget | None = None
        self._chat_history_panel: QTextEdit | None = None
        self._chat_input: QTextEdit | None = None
        self._chat_send_button: QPushButton | None = None
        self._chat_notice: QLabel | None = None
        self._chat_worker: "_ChatWorker | None" = None
        self._active_task: QLabel | None = None
        self._stack: QStackedWidget | None = None
        self._last_state: DashboardState | None = None
        self._notifications_open = False
        self._sidebar_expanded = True
        self._focus_mode = False
        self._tick = 0
        self._last_completed_count = 0

        self.setWindowTitle("Synapse Labs - IRIS Vision")
        self.setMinimumSize(1320, 820)
        self._build_ui()
        self._install_actions()
        self._apply_styles()
        self._configure_timers()
        self._refresh()

    def _build_ui(self) -> None:
        root = QWidget(self)
        root.setObjectName("root")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._sidebar = self._build_sidebar(root)
        root_layout.addWidget(self._sidebar)

        self._stage = QFrame(root)
        self._stage.setObjectName("stage")
        stage_layout = QVBoxLayout(self._stage)
        stage_layout.setContentsMargins(18, 14, 18, 14)
        stage_layout.setSpacing(12)
        self._top_bar = self._build_top_bar(self._stage)
        stage_layout.addWidget(self._top_bar)

        canvas = QFrame(self._stage)
        canvas.setObjectName("canvas")
        canvas_layout = QGridLayout(canvas)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(0)
        self._background = NeuralBackground(canvas)
        canvas_layout.addWidget(self._background, 0, 0)

        overlay = QWidget(canvas)
        overlay.setObjectName("overlay")
        overlay_layout = QGridLayout(overlay)
        overlay_layout.setContentsMargins(18, 18, 18, 18)
        overlay_layout.setSpacing(18)
        self._stack = QStackedWidget(overlay)
        self._stack.setObjectName("pageStack")
        for key, _, _ in self.PAGES:
            page = self._build_page(key)
            self._pages[key] = page
            self._stack.addWidget(page)
        overlay_layout.addWidget(self._stack, 0, 0)
        canvas_layout.addWidget(overlay, 0, 0)
        stage_layout.addWidget(canvas, stretch=1)

        root_layout.addWidget(self._stage, stretch=1)
        self._notification_panel = self._build_notification_panel(root)
        self._notification_panel.setMaximumWidth(0)
        root_layout.addWidget(self._notification_panel)
        self.setCentralWidget(root)
        self._select_page("mission")

    def _build_sidebar(self, parent: QWidget) -> QFrame:
        sidebar = QFrame(parent)
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(264)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 18, 16, 18)
        layout.setSpacing(10)

        brand = QLabel("Synapse Labs\nIRIS Vision", sidebar)
        brand.setObjectName("brand")
        layout.addWidget(brand)

        collapse = QToolButton(sidebar)
        collapse.setObjectName("collapseButton")
        collapse.setToolTip("Collapse sidebar")
        collapse.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarShadeButton))
        collapse.clicked.connect(self._toggle_sidebar)
        layout.addWidget(collapse)

        for key, title, icon_id in self.PAGES:
            button = QToolButton(sidebar)
            button.setObjectName("navButton")
            button.setText(title)
            button.setToolTip(title)
            button.setIcon(self.style().standardIcon(icon_id))
            button.setIconSize(QSize(22, 22))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.clicked.connect(lambda _checked=False, page_key=key: self._select_page(page_key))
            self._page_buttons[key] = button
            layout.addWidget(button)

        layout.addStretch(1)
        return sidebar

    def _build_top_bar(self, parent: QWidget) -> QFrame:
        top = QFrame(parent)
        top.setObjectName("topBar")
        layout = QHBoxLayout(top)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        title = QLabel("IRIS AI Operating System", top)
        title.setObjectName("topTitle")
        layout.addWidget(title)
        layout.addStretch(1)

        for key in ("status", "time", "cpu", "ram", "user"):
            label = QLabel("--", top)
            label.setObjectName("statusPill")
            self._status_labels[key] = label
            layout.addWidget(label)

        notify = QToolButton(top)
        notify.setObjectName("roundTool")
        notify.setToolTip("Notification Center")
        notify.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation))
        notify.clicked.connect(self._toggle_notifications)
        layout.addWidget(notify)
        self._notification_badge = QLabel("0", top)
        self._notification_badge.setObjectName("unreadBadge")
        layout.addWidget(self._notification_badge)
        return top

    def _build_page(self, key: str) -> QWidget:
        if key == "mission":
            return self._build_mission_page()
        if key == "chat":
            return self._build_chat_page()
        if key == "workflow":
            return self._build_workflow_page()
        if key == "router":
            return self._build_router_page()
        if key == "research":
            return self._build_research_page()
        if key == "studio":
            return self._build_studio_page()
        if key == "analytics":
            return self._build_analytics_page()
        if key == "scheduler":
            return self._build_scheduler_page()
        if key == "telegram":
            return self._build_console_page("telegram", "Telegram Timeline")
        if key == "voice":
            return self._build_voice_page()
        return self._build_settings_page()

    def _build_mission_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("visionPage")
        layout = QGridLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        left = QGridLayout()
        for index, (key, title) in enumerate(
            (
                ("cpu", "CPU"),
                ("gpu", "GPU"),
                ("ram", "RAM"),
                ("vram", "VRAM"),
                ("disk", "Disk"),
                ("network", "Network"),
                ("agents", "Running Agents"),
                ("queue", "Queue"),
            )
        ):
            card = MetricTile(title)
            self._metric_labels[key] = card.value
            self._focus_widgets.append(card)
            left.addWidget(card, index // 2, index % 2)

        center = QWidget(page)
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(12)
        self._core = IrisCoreWidget(center)
        center_layout.addWidget(self._core, stretch=3)
        self._active_task = QLabel("Current active task: standby", center)
        self._active_task.setObjectName("activeTask")
        self._active_task.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(self._active_task)
        self._panels["mission_status"] = self._text_panel("Mission Stream")
        center_layout.addWidget(self._panels["mission_status"], stretch=2)

        right = QVBoxLayout()
        for key, title in (("workflow_status", "Workflow Status"), ("provider_status", "Provider Status")):
            panel = self._text_panel(title)
            self._panels[key] = panel
            if key == "provider_status":
                self._focus_widgets.append(panel)
            right.addWidget(panel)

        layout.addLayout(left, 0, 0)
        layout.addWidget(center, 0, 1)
        layout.addLayout(right, 0, 2)
        layout.setColumnStretch(0, 2)
        layout.setColumnStretch(1, 3)
        layout.setColumnStretch(2, 2)
        return page

    def _build_workflow_page(self) -> QWidget:
        page = self._scroll_page()
        layout = self._page_layout(page)
        layout.addWidget(self._action_strip(page))
        self._workflow_graph = WorkflowGraph(page)
        layout.addWidget(self._workflow_graph)
        self._panels["workflow_timeline"] = self._text_panel("Workflow Timeline")
        layout.addWidget(self._panels["workflow_timeline"])
        return page

    def _build_router_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("visionPage")
        layout = QGridLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        orbit = QFrame(page)
        orbit.setObjectName("orbitPanel")
        orbit_layout = QGridLayout(orbit)
        orbit_layout.setContentsMargins(18, 18, 18, 18)
        refresh = QPushButton("Refresh", orbit)
        refresh.clicked.connect(self._refresh)
        orbit_layout.addWidget(refresh, 0, 0, 1, 3)
        providers = ("Mock", "Provider 2", "Provider 3", "Provider 4", "Provider 5", "Provider 6", "Future Providers")
        for index, provider in enumerate(providers):
            card = OrbitCard(provider)
            self._providers.append(card)
            self._focus_widgets.append(card)
            orbit_layout.addWidget(card, index // 3 + 1, index % 3)
        layout.addWidget(orbit, 0, 0)
        self._focus_widgets.append(orbit)
        self._panels["router_status"] = self._text_panel("Provider Telemetry")
        layout.addWidget(self._panels["router_status"], 0, 1)
        layout.setColumnStretch(0, 3)
        layout.setColumnStretch(1, 2)
        return page

    def _build_research_page(self) -> QWidget:
        page = self._scroll_page()
        layout = self._page_layout(page)
        strip = QFrame(page)
        strip.setObjectName("glass")
        strip_layout = QHBoxLayout(strip)
        strip_layout.setContentsMargins(14, 12, 14, 12)
        scan = QPushButton("Start Scan", strip)
        scan.clicked.connect(self._request_research_scan)
        stop = QPushButton("Stop Scan", strip)
        stop.clicked.connect(self._request_research_stop)
        strip_layout.addWidget(scan)
        strip_layout.addWidget(stop)
        strip_layout.addStretch(1)
        layout.addWidget(strip)
        self._panels["research_topics"] = self._text_panel("Trending Topic Cards")
        layout.addWidget(self._panels["research_topics"])
        chart = LiveChart("Research Scores")
        self._charts["research_scores"] = chart
        layout.addWidget(chart)
        return page

    def _build_studio_page(self) -> QWidget:
        page = self._scroll_page()
        layout = self._page_layout(page)
        grid = QGridLayout()
        for index, (key, title) in enumerate(
            (
                ("video_queue", "Video Queue"),
                ("thumbnail", "Thumbnail Preview"),
                ("upload", "Upload Progress"),
                ("studio_analytics", "Analytics"),
            )
        ):
            tile = MetricTile(title)
            self._metric_labels[key] = tile.value
            self._focus_widgets.append(tile)
            grid.addWidget(tile, index // 2, index % 2)
        layout.addLayout(grid)
        self._panels["studio_history"] = self._text_panel("Studio History")
        layout.addWidget(self._panels["studio_history"])
        return page

    def _build_analytics_page(self) -> QWidget:
        page = self._scroll_page()
        layout = self._page_layout(page)
        grid = QGridLayout()
        for index, name in enumerate(("CPU", "GPU", "RAM", "VRAM", "Disk", "Queue", "Network", "Requests")):
            chart = LiveChart(name)
            self._charts[f"analytics_{name.lower()}"] = chart
            self._focus_widgets.append(chart)
            grid.addWidget(chart, index // 2, index % 2)
        layout.addLayout(grid)
        return page

    def _build_scheduler_page(self) -> QWidget:
        return self._build_console_page("scheduler", "Scheduler Timeline")

    def _build_voice_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("visionPage")
        layout = QGridLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        left = QFrame(page)
        left.setObjectName("glass")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(14, 14, 14, 14)
        left_layout.setSpacing(10)
        title = QLabel("Voice Session", left)
        title.setObjectName("sectionTitle")
        self._voice_history = self._text_panel("Conversation History")
        self._voice_history.setMinimumHeight(300)
        input_row = QHBoxLayout()
        self._voice_input = QLineEdit(left)
        self._voice_input.setPlaceholderText("Message IRIS")
        self._voice_input.returnPressed.connect(self._send_voice_message)
        send = QPushButton("Send", left)
        send.clicked.connect(self._send_voice_message)
        voice = QPushButton("Voice", left)
        voice.clicked.connect(self._toggle_voice_listening)
        input_row.addWidget(self._voice_input, stretch=1)
        input_row.addWidget(send)
        input_row.addWidget(voice)
        left_layout.addWidget(title)
        left_layout.addWidget(self._voice_history, stretch=1)
        left_layout.addLayout(input_row)

        center = QFrame(page)
        center.setObjectName("glass")
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(12, 12, 12, 12)
        self._voice_core = IrisCoreWidget(center)
        self._voice_core.set_state("listening")
        self._voice_waveform = VoiceWaveform(center)
        center_layout.addWidget(self._voice_core, stretch=3)
        center_layout.addWidget(self._voice_waveform)

        right = QFrame(page)
        right.setObjectName("glass")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(14, 14, 14, 14)
        right_layout.setSpacing(10)
        settings = QLabel("Voice Settings", right)
        settings.setObjectName("sectionTitle")
        self._voice_mic_status = QLabel("Microphone: standby", right)
        self._voice_mic_status.setObjectName("cardLabel")
        provider_label = QLabel("Current provider", right)
        provider_label.setObjectName("cardLabel")
        self._voice_provider = QComboBox(right)
        self._voice_provider.addItems(("Local Bridge", "OpenAI Realtime", "System TTS", "Future Provider"))
        vad = QCheckBox("Voice activity detection", right)
        vad.setChecked(True)
        vad.setObjectName("voiceCheck")
        sensitivity_label = QLabel("Input sensitivity", right)
        sensitivity_label.setObjectName("cardLabel")
        sensitivity = QSlider(Qt.Orientation.Horizontal, right)
        sensitivity.setRange(0, 100)
        sensitivity.setValue(62)
        self._panels["voice_console"] = self._text_panel("Conversation Log")
        right_layout.addWidget(settings)
        right_layout.addWidget(self._voice_mic_status)
        right_layout.addWidget(provider_label)
        right_layout.addWidget(self._voice_provider)
        right_layout.addWidget(vad)
        right_layout.addWidget(sensitivity_label)
        right_layout.addWidget(sensitivity)
        right_layout.addWidget(self._panels["voice_console"], stretch=1)

        layout.addWidget(left, 0, 0)
        layout.addWidget(center, 0, 1)
        layout.addWidget(right, 0, 2)
        layout.setColumnStretch(0, 3)
        layout.setColumnStretch(1, 3)
        layout.setColumnStretch(2, 2)
        return page

    def _build_chat_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("visionPage")
        layout = QGridLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        left = QFrame(page)
        left.setObjectName("glass")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(14, 14, 14, 14)
        left_layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("IRIS Chat", left)
        title.setObjectName("sectionTitle")
        copy_button = QPushButton("Copy Response", left)
        copy_button.clicked.connect(self._copy_last_chat_response)
        clear_button = QPushButton("Clear", left)
        clear_button.clicked.connect(self._clear_chat)
        header.addWidget(title, stretch=1)
        header.addWidget(copy_button)
        header.addWidget(clear_button)

        self._chat_history_panel = self._text_panel("IRIS Chat")
        self._chat_history_panel.setObjectName("timelinePanel")
        self._chat_history_panel.setMinimumHeight(360)

        self._chat_notice = QLabel("", left)
        self._chat_notice.setObjectName("cardLabel")
        self._chat_notice.setVisible(False)

        self._chat_input = QTextEdit(left)
        self._chat_input.setObjectName("textPanel")
        self._chat_input.setPlaceholderText("Message IRIS...")
        self._chat_input.setFixedHeight(84)

        input_row = QHBoxLayout()
        self._chat_send_button = QPushButton("Send", left)
        self._chat_send_button.clicked.connect(self._send_chat_message)
        input_row.addWidget(self._chat_input, stretch=1)
        input_row.addWidget(self._chat_send_button)

        left_layout.addLayout(header)
        left_layout.addWidget(self._chat_history_panel, stretch=1)
        left_layout.addWidget(self._chat_notice)
        left_layout.addLayout(input_row)

        right = QFrame(page)
        right.setObjectName("glass")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 12, 12, 12)
        self._chat_core = IrisCoreWidget(right)
        self._chat_core.set_state("idle")
        right_layout.addWidget(self._chat_core, stretch=1)

        layout.addWidget(left, 0, 0)
        layout.addWidget(right, 0, 1)
        layout.setColumnStretch(0, 3)
        layout.setColumnStretch(1, 2)

        self._render_chat_history()
        return page

    def _render_chat_history(self) -> None:
        if self._chat_history_panel is None:
            return
        messages = self._view_model.chat_history()
        if not messages:
            body = "<div style=\"color:#7fb8d9;\">Say hello to IRIS to begin.</div>"
        else:
            body = "".join(self._chat_message_html(message) for message in messages)
        self._chat_history_panel.setAcceptRichText(True)
        self._chat_history_panel.setHtml(self._html_doc("IRIS Chat", body))
        scrollbar = self._chat_history_panel.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _chat_message_html(self, message: ChatMessage) -> str:
        is_user = message.role == "user"
        align = "right" if is_user else "left"
        bubble_color = "rgba(42,190,255,.16)" if is_user else "rgba(178,98,255,.14)"
        border_color = "rgba(42,190,255,.45)" if is_user else "rgba(178,98,255,.45)"
        speaker = "You" if is_user else "IRIS"
        badges = f"<span style=\"color:#7fb8d9;\">{escape(message.timestamp)}</span>"
        if message.provider:
            badges += f" &middot; <span style=\"color:#8be9ff;\">{escape(message.provider)}</span>"
        if message.latency_ms is not None:
            badges += f" &middot; <span style=\"color:#8be9ff;\">{message.latency_ms:.0f} ms</span>"
        return (
            f"<div style=\"text-align:{align};margin:0 0 12px 0;\">"
            f"<div style=\"display:inline-block;max-width:78%;text-align:left;"
            f"background:{bubble_color};border:1px solid {border_color};border-radius:10px;"
            f"padding:10px 14px;\">"
            f"<div style=\"font-size:12px;font-weight:700;color:#ffffff;margin-bottom:4px;\">{escape(speaker)}</div>"
            f"<div style=\"font-size:13px;color:#e8f5ff;white-space:pre-wrap;\">{escape(message.text)}</div>"
            f"<div style=\"font-size:11px;margin-top:6px;\">{badges}</div>"
            f"</div></div>"
        )

    def _send_chat_message(self) -> None:
        if self._chat_input is None or self._chat_worker is not None:
            return
        text = self._chat_input.toPlainText().strip()
        if not text:
            return
        self._chat_input.clear()
        self._view_model.append_user_message(text)
        self._render_chat_history()
        if self._chat_notice is not None:
            self._chat_notice.setVisible(False)
        if self._chat_core is not None:
            self._chat_core.set_state("thinking")
        if self._chat_send_button is not None:
            self._chat_send_button.setEnabled(False)

        worker = _ChatWorker(self._view_model, self)
        worker.completed.connect(self._on_chat_response)
        worker.finished.connect(self._on_chat_worker_finished)
        self._chat_worker = worker
        worker.start()

    def _on_chat_response(self, result: ChatResult) -> None:
        self._render_chat_history()
        if self._chat_core is not None:
            self._chat_core.set_speech(result.message.text)
        if self._chat_notice is not None:
            if result.notice:
                self._chat_notice.setText(result.notice)
                self._chat_notice.setVisible(True)
            else:
                self._chat_notice.setVisible(False)

    def _on_chat_worker_finished(self) -> None:
        self._chat_worker = None
        if self._chat_send_button is not None:
            self._chat_send_button.setEnabled(True)

    def _clear_chat(self) -> None:
        self._view_model.clear_chat()
        self._render_chat_history()
        if self._chat_notice is not None:
            self._chat_notice.setVisible(False)
        if self._chat_core is not None:
            self._chat_core.set_state("idle")

    def _copy_last_chat_response(self) -> None:
        for message in reversed(self._view_model.chat_history()):
            if message.role == "assistant":
                clipboard = QApplication.clipboard()
                if clipboard is not None:
                    clipboard.setText(message.text)
                break

    def _build_settings_page(self) -> QWidget:
        return self._build_console_page("settings", "System Services")

    def _build_console_page(self, key: str, title: str) -> QWidget:
        page = self._scroll_page()
        layout = self._page_layout(page)
        self._panels[key] = self._text_panel(title)
        layout.addWidget(self._panels[key])
        return page

    def _build_notification_panel(self, parent: QWidget) -> QFrame:
        panel = QFrame(parent)
        panel.setObjectName("notificationPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        title = QLabel("Notification Center", panel)
        title.setObjectName("sectionTitle")
        self._notification_search = QLineEdit(panel)
        self._notification_search.setPlaceholderText("Search timeline")
        self._notification_filter = QLineEdit(panel)
        self._notification_filter.setPlaceholderText("Filter source or state")
        self._notification_text = self._text_panel("Notifications")
        self._notification_text.setObjectName("timelinePanel")
        self._notification_search.textChanged.connect(self._render_cached_notifications)
        self._notification_filter.textChanged.connect(self._render_cached_notifications)
        layout.addWidget(title)
        layout.addWidget(self._notification_search)
        layout.addWidget(self._notification_filter)
        layout.addWidget(self._notification_text, stretch=1)
        return panel

    def _scroll_page(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName("scrollPage")
        scroll.setWidgetResizable(True)
        page = QWidget(scroll)
        page.setObjectName("visionPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        scroll.setWidget(page)
        return scroll

    def _page_layout(self, page: QWidget) -> QVBoxLayout:
        if isinstance(page, QScrollArea) and page.widget() is not None:
            layout = page.widget().layout()
            if isinstance(layout, QVBoxLayout):
                return layout
        raise TypeError("Vision page requires a QVBoxLayout")

    def _text_panel(self, title: str) -> QTextEdit:
        panel = QTextEdit()
        panel.setObjectName("textPanel")
        panel.setAccessibleName(title)
        panel.setReadOnly(True)
        panel.setMinimumHeight(220)
        return panel

    def _action_strip(self, parent: QWidget) -> QFrame:
        strip = QFrame(parent)
        strip.setObjectName("glass")
        layout = QHBoxLayout(strip)
        layout.setContentsMargins(14, 12, 14, 12)
        for title, callback in (
            ("Run", self._run_first_workflow),
            ("Pause", self._pause_latest_execution),
            ("Resume", self._resume_latest_execution),
            ("Retry", self._retry_latest_execution),
            ("Cancel", self._cancel_latest_execution),
        ):
            button = QPushButton(title, strip)
            button.clicked.connect(callback)
            layout.addWidget(button)
        layout.addStretch(1)
        return strip

    def _install_actions(self) -> None:
        focus = QAction(self)
        focus.setShortcut("Ctrl+Shift+F")
        focus.triggered.connect(self._toggle_focus_mode)
        self.addAction(focus)

    def _configure_timers(self) -> None:
        refresh = QTimer(self)
        refresh.timeout.connect(self._refresh)
        refresh.start(1000)
        frame = QTimer(self)
        frame.timeout.connect(self._animate_frame)
        frame.start(16)

    def _refresh(self) -> None:
        state = self._view_model.snapshot()
        self._last_state = state
        self._render_state(state)

    def _animate_frame(self) -> None:
        self._tick += 1
        phase = self._tick / 30.0
        if self._background is not None:
            self._background.set_phase(phase, self._focus_mode)
        if self._core is not None:
            self._core.set_phase(phase)
        if self._voice_core is not None:
            self._voice_core.set_phase(phase)
        if self._voice_waveform is not None:
            self._voice_waveform.set_phase(phase, self._voice_core.state if self._voice_core is not None else "idle")
        if self._workflow_graph is not None:
            self._workflow_graph.set_phase(phase)
        for chart in self._charts.values():
            chart.pulse()

    def _render_state(self, state: DashboardState) -> None:
        metrics = state.metrics
        workflows = state.workflows
        queue_size = state.queue_size
        running = workflows.get("running", [])
        completed = workflows.get("completed", [])
        failed = workflows.get("failed", [])
        gpu = min(100.0, max(4.0, metrics.cpu_percent * 0.45 + queue_size * 4.0))
        network = min(100.0, 12.0 + queue_size * 8.0 + (self._tick % 40))
        disk = min(100.0, 18.0 + len(state.logs) % 70)

        values = {
            "cpu": f"{metrics.cpu_percent:.1f}%",
            "gpu": f"{gpu:.1f}%",
            "ram": f"{metrics.ram_percent:.1f}%",
            "vram": f"{min(100.0, gpu * .72):.1f}%",
            "disk": f"{disk:.1f}%",
            "network": f"{network:.1f}%",
            "agents": str(state.registered_agents),
            "queue": str(queue_size),
            "video_queue": str(queue_size),
            "thumbnail": str(state.youtube_agent.get("last_generated_video", "--")),
            "upload": f"{state.youtube_agent.get('upload_progress', 0)}%",
            "studio_analytics": f"{len(state.youtube_agent.get('recent_events', []))} events",
        }
        for key, value in values.items():
            if key in self._metric_labels:
                self._metric_labels[key].setText(value)

        self._status_labels["status"].setText(state.iris_status)
        self._status_labels["time"].setText(metrics.current_time)
        self._status_labels["cpu"].setText(f"CPU {metrics.cpu_percent:.1f}%")
        self._status_labels["ram"].setText(f"RAM {metrics.ram_percent:.1f}%")
        self._status_labels["user"].setText(getuser())

        core_state = "error" if failed else "workflow" if running else "thinking" if queue_size else "idle"
        if self._core is not None:
            self._core.set_state(core_state)
            if len(completed) > self._last_completed_count:
                self._core.set_speech("Workflow completed.\nIRIS systems are synchronized.")
        self._last_completed_count = len(completed)
        if self._active_task is not None:
            task = "workflow running" if running else "queue pending" if queue_size else "standby"
            self._active_task.setText(f"Current active task: {task}")

        chart_values = {
            "analytics_cpu": metrics.cpu_percent,
            "analytics_gpu": gpu,
            "analytics_ram": metrics.ram_percent,
            "analytics_vram": min(100.0, gpu * .72),
            "analytics_disk": disk,
            "analytics_queue": min(100.0, queue_size * 14.0),
            "analytics_network": network,
            "analytics_requests": min(100.0, state.completed_tasks * 4.0),
            "research_scores": self._research_score(state),
        }
        for key, value in chart_values.items():
            if key in self._charts:
                self._charts[key].append(value)

        self._render_workflows(state)
        self._render_research(state)
        self._render_studio(state)
        self._render_router(state)
        self._render_scheduler(state)
        self._render_services(state)
        self._render_notifications(state)

    def _render_workflows(self, state: DashboardState) -> None:
        workflows = state.workflows
        executions = workflows.get("executions", [])
        running = workflows.get("running", [])
        queued = workflows.get("queued", [])
        completed = workflows.get("completed", [])
        lines = [
            f"Running: {len(running)}",
            f"Queued: {len(queued)}",
            f"Completed: {len(completed)}",
            "",
        ]
        for execution in executions[-12:]:
            if isinstance(execution, dict):
                lines.append(
                    f"{execution.get('status', 'Queued')} | {execution.get('workflow_id', 'workflow')} | "
                    f"step {execution.get('current_step', '--')} | retries {execution.get('retry_count', 0)}"
                )
        self._set_panel("workflow_timeline", lines or ["No workflow executions yet."])
        self._set_panel("workflow_status", lines[:20] or ["Workflow engine online."])

    def _render_research(self, state: DashboardState) -> None:
        topics = state.research_agent.get("top_ranked_topics", [])
        cards = []
        for topic in topics:
            if not isinstance(topic, dict):
                continue
            cards.append(
                self._html_card(
                    str(topic.get("title", "Untitled topic")),
                    f"Score {topic.get('score', '--')} | Confidence {topic.get('confidence', '--')} | "
                    f"{topic.get('provider', '--')} | {topic.get('category', '--')}",
                )
            )
        provider_lines = [
            f"{item.get('name', '--')}: {item.get('status', '--')}"
            for item in state.research_agent.get("provider_status", [])
            if isinstance(item, dict)
        ]
        self._set_panel_html("research_topics", self._html_doc("Trending", "".join(cards) or "<p>No trending topics available.</p>"))
        self._append_panel("provider_status", ["Research Providers", *provider_lines])

    def _render_studio(self, state: DashboardState) -> None:
        events = state.youtube_agent.get("recent_events", [])
        lines = [
            f"Status: {state.youtube_agent.get('status', 'Unavailable')}",
            f"Current task: {state.youtube_agent.get('current_task', '--')}",
            f"Render: {state.youtube_agent.get('render_progress', 0)}%",
            f"Upload: {state.youtube_agent.get('upload_progress', 0)}%",
            "",
        ]
        for event in events[-20:]:
            if isinstance(event, dict):
                lines.append(f"{event.get('created_at', '')} | {event.get('name', '')} | {event.get('payload', {})}")
        self._set_panel("studio_history", lines)

    def _render_router(self, state: DashboardState) -> None:
        provider_status = [
            item for item in state.ai_router.get("provider_status", []) if isinstance(item, dict)
        ]
        lines = [
            f"Routing mode: {state.ai_router.get('routing_mode', '--')}",
            f"Current provider: {state.ai_router.get('current_provider', '--')}",
            "",
            "Registered Providers",
        ]
        for index, card in enumerate(self._providers):
            provider = provider_status[index] if index < len(provider_status) else None
            if provider is None:
                card.set_rows("Future", "--", "0", active=False)
                continue

            name = str(provider.get("name", "--"))
            status = str(provider.get("status", "--"))
            latency = provider.get("latency_ms")
            latency_text = "--" if latency is None else f"{float(latency):.1f} ms"
            health = "Healthy" if provider.get("available") else "Unavailable"
            current = name == state.ai_router.get("current_provider")
            card.title.setText(name.title())
            card.set_rows(status, latency_text, health, active=current)
            lines.append(
                f"{name} | {status} | Health {health} | Latency {latency_text} | "
                f"Last success {provider.get('last_successful_request') or '--'}"
            )
        if not provider_status:
            lines.append("No providers registered.")
        self._set_panel("router_status", lines)
        self._set_panel("provider_status", lines)

    def _render_scheduler(self, state: DashboardState) -> None:
        schedules = state.scheduler.get("schedules", [])
        upcoming = state.scheduler.get("upcoming", [])
        lines = ["Upcoming"]
        for item in upcoming:
            lines.append(str(item))
        lines.append("")
        lines.append("Schedules")
        for item in schedules:
            lines.append(str(item))
        self._set_panel("scheduler", lines if len(lines) > 3 else ["No schedules registered."])

    def _render_services(self, state: DashboardState) -> None:
        cards = []
        for service in state.services:
            name = str(service.get("name", "Service"))
            status = str(service.get("status", "--"))
            health = "Healthy" if service.get("healthy", False) else "Attention"
            cards.append(self._html_card(name, f"{health} | {status} | v{service.get('version', '--')}"))
        self._set_panel_html("settings", self._html_doc("System Services", "".join(cards)))
        self._set_panel("telegram", state.logs[-80:] or ["No Telegram events in the current log stream."])
        provider = self._voice_provider.currentText() if self._voice_provider is not None else "Local Bridge"
        self._set_panel(
            "voice_console",
            [
                f"Provider: {provider}",
                "STT integration point: voice input bridge",
                "TTS integration point: IRIS Core speech cloud",
                "Conversation events are local until a voice backend is registered.",
            ],
        )
        self._set_panel("mission_status", state.logs[-80:] or ["IRIS Core online."])

    def _render_cached_notifications(self) -> None:
        if self._last_state is not None:
            self._render_notifications(self._last_state)

    def _render_notifications(self, state: DashboardState) -> None:
        if self._notification_text is None:
            return
        search = self._notification_search.text().lower() if self._notification_search else ""
        filter_value = self._notification_filter.text().lower() if self._notification_filter else ""
        lines = []
        for line in state.logs[-240:]:
            normalized = line.lower()
            if search and search not in normalized:
                continue
            if filter_value and filter_value not in normalized:
                continue
            lines.append(line)
        unread = len(lines)
        if self._notification_badge is not None:
            self._notification_badge.setText(str(min(99, unread)))
            self._notification_badge.setProperty("attention", unread > 0)
            self._notification_badge.style().unpolish(self._notification_badge)
            self._notification_badge.style().polish(self._notification_badge)
        timeline = []
        for index, line in enumerate(lines[-140:]):
            marker = "NEW" if index >= max(0, len(lines[-140:]) - 5) else "LOG"
            timeline.append(f"{marker}  {line}")
        self._notification_text.setPlainText("\n".join(timeline))

    def _set_panel(self, key: str, lines: list[str]) -> None:
        panel = self._panels.get(key)
        if panel is not None:
            panel.setAcceptRichText(False)
            panel.setPlainText("\n".join(lines))

    def _append_panel(self, key: str, lines: list[str]) -> None:
        panel = self._panels.get(key)
        if panel is not None:
            existing = panel.toPlainText()
            merged = [line for line in existing.splitlines() if line]
            panel.setPlainText("\n".join([*merged[:18], "", *lines]))

    def _set_panel_html(self, key: str, html: str) -> None:
        panel = self._panels.get(key)
        if panel is not None:
            panel.setAcceptRichText(True)
            panel.setHtml(html)

    def _html_doc(self, title: str, body: str) -> str:
        return (
            "<html><body style=\"background:#07101b;color:#e8f5ff;"
            "font-family:'Segoe UI',sans-serif;\">"
            f"<h2 style=\"margin:0 0 12px 0;color:#ffffff;\">{escape(title)}</h2>{body}</body></html>"
        )

    def _html_card(self, title: str, detail: str) -> str:
        return (
            "<div style=\"border:1px solid rgba(80,200,255,.35);border-radius:8px;"
            "padding:12px;margin:0 0 10px 0;background:rgba(9,24,42,.78);\">"
            f"<div style=\"font-size:15px;font-weight:700;color:#fff;\">{escape(title)}</div>"
            f"<div style=\"font-size:12px;color:#a7dfff;margin-top:5px;\">{escape(detail)}</div></div>"
        )

    def _research_score(self, state: DashboardState) -> float:
        topics = state.research_agent.get("top_ranked_topics", [])
        values = [float(topic.get("score", 0.0)) for topic in topics if isinstance(topic, dict)]
        if not values:
            return 0.0
        return max(0.0, min(100.0, sum(values[:8]) / min(len(values), 8)))

    def _select_page(self, key: str) -> None:
        if self._stack is None:
            return
        page = self._pages.get(key)
        if page is not None:
            self._stack.setCurrentWidget(page)
        for page_key, button in self._page_buttons.items():
            visible = not self._focus_mode or page_key in {"mission", "workflow", "voice", "settings"}
            button.setVisible(visible)
            button.setProperty("active", page_key == key)
            button.style().unpolish(button)
            button.style().polish(button)
        self._fade_current_page()

    def _fade_current_page(self) -> None:
        if self._stack is None:
            return
        widget = self._stack.currentWidget()
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", widget)
        animation.setDuration(210)
        animation.setStartValue(0.2)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(lambda: widget.setGraphicsEffect(None))
        animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def _toggle_sidebar(self) -> None:
        if self._sidebar is None:
            return
        self._sidebar_expanded = not self._sidebar_expanded
        width = 264 if self._sidebar_expanded else 82
        for prop in (b"minimumWidth", b"maximumWidth"):
            animation = QPropertyAnimation(self._sidebar, prop, self)
            animation.setDuration(240)
            animation.setStartValue(self._sidebar.width())
            animation.setEndValue(width)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        for button in self._page_buttons.values():
            button.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextBesideIcon if self._sidebar_expanded else Qt.ToolButtonStyle.ToolButtonIconOnly
            )

    def _toggle_notifications(self) -> None:
        if self._notification_panel is None:
            return
        self._notifications_open = not self._notifications_open
        if self._focus_mode and self._notifications_open:
            self._notifications_open = False
            return
        animation = QPropertyAnimation(self._notification_panel, b"maximumWidth", self)
        animation.setDuration(260)
        animation.setStartValue(self._notification_panel.maximumWidth())
        animation.setEndValue(390 if self._notifications_open else 0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        if self._stage is not None:
            if self._notifications_open:
                blur = QGraphicsBlurEffect(self._stage)
                blur.setBlurRadius(1.6)
                self._stage.setGraphicsEffect(blur)
            else:
                self._stage.setGraphicsEffect(None)

    def _toggle_focus_mode(self) -> None:
        self._focus_mode = not self._focus_mode
        if self._core is not None:
            self._core.set_focus(self._focus_mode)
        if self._voice_core is not None:
            self._voice_core.set_focus(self._focus_mode)
        if self._focus_mode and self._notifications_open:
            self._notifications_open = False
            if self._notification_panel is not None:
                self._notification_panel.setMaximumWidth(0)
            if self._stage is not None:
                self._stage.setGraphicsEffect(None)
        self.setProperty("focusMode", self._focus_mode)
        self.style().unpolish(self)
        self.style().polish(self)
        for widget in self._focus_widgets:
            self._fade_widget_visible(widget, not self._focus_mode)
        if self._top_bar is not None:
            for label in self._status_labels.values():
                label.setVisible(not self._focus_mode)
        for key, button in self._page_buttons.items():
            button.setVisible(not self._focus_mode or key in {"mission", "workflow", "voice", "settings"})
        if self._stack is not None and self._focus_mode and self._stack.currentWidget() not in {
            self._pages["mission"],
            self._pages["workflow"],
            self._pages["voice"],
            self._pages["settings"],
        }:
            self._select_page("mission")

    def _fade_widget_visible(self, widget: QWidget, visible: bool) -> None:
        if visible:
            widget.setVisible(True)
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", widget)
        animation.setDuration(180)
        animation.setStartValue(0.0 if visible else 1.0)
        animation.setEndValue(1.0 if visible else 0.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        if not visible:
            animation.finished.connect(lambda: widget.setVisible(False))
        animation.finished.connect(lambda: widget.setGraphicsEffect(None))
        animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def _send_voice_message(self) -> None:
        """Voice input hook. Speech recognition/synthesis ship in Sprint 9;
        for now this only demonstrates the integration point (mic text -> IRIS)
        without claiming to route anywhere real."""
        if self._voice_input is None:
            return
        message = self._voice_input.text().strip()
        if not message:
            return
        self._voice_input.clear()
        response = "IRIS: This feature will be available in Sprint 9."
        if self._voice_history is not None:
            current = self._voice_history.toPlainText().strip()
            next_text = "\n".join(part for part in (current, f"You: {message}", response) if part)
            self._voice_history.setPlainText(next_text)
            self._voice_history.verticalScrollBar().setValue(self._voice_history.verticalScrollBar().maximum())
        if self._voice_core is not None:
            self._voice_core.set_speech(response.replace("IRIS: ", ""))

    def _toggle_voice_listening(self) -> None:
        if self._voice_core is None:
            return
        next_state = "idle" if self._voice_core.state == "listening" else "listening"
        self._voice_core.set_state(next_state)
        if self._core is not None:
            self._core.set_state(next_state)
        if self._voice_mic_status is not None:
            self._voice_mic_status.setText(f"Microphone: {next_state}")

    def _request_research_scan(self) -> None:
        self._view_model.request_research_scan()
        self._refresh()

    def _request_research_stop(self) -> None:
        self._view_model.request_research_stop()
        self._refresh()

    def _run_first_workflow(self) -> None:
        workflows = self._view_model.snapshot().workflows.get("workflows", [])
        if workflows:
            self._view_model.run_workflow(str(workflows[0].get("workflow_id", "")))
        self._refresh()

    def _pause_latest_execution(self) -> None:
        execution_id = self._latest_execution_id()
        if execution_id:
            self._view_model.pause_workflow(execution_id)
        self._refresh()

    def _resume_latest_execution(self) -> None:
        execution_id = self._latest_execution_id()
        if execution_id:
            self._view_model.resume_workflow(execution_id)
        self._refresh()

    def _retry_latest_execution(self) -> None:
        execution_id = self._latest_execution_id()
        if execution_id:
            self._view_model.retry_workflow(execution_id)
        self._refresh()

    def _cancel_latest_execution(self) -> None:
        execution_id = self._latest_execution_id()
        if execution_id:
            self._view_model.cancel_workflow(execution_id)
        self._refresh()

    def _latest_execution_id(self) -> str | None:
        executions = self._view_model.snapshot().workflows.get("executions", [])
        if not executions:
            return None
        latest = executions[-1]
        return str(latest.get("execution_id")) if isinstance(latest, dict) else None

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget#root {
                background-color: #03070d;
                color: #e9f7ff;
                font-family: "Segoe UI", "Inter", sans-serif;
            }
            QMainWindow[focusMode="true"], QMainWindow[focusMode="true"] QWidget#root {
                background-color: #050303;
                color: #ffe9e9;
            }
            QFrame#stage, QWidget#overlay, QWidget#visionPage {
                background: transparent;
            }
            QFrame#sidebar {
                background-color: rgba(5, 13, 24, 235);
                border-right: 1px solid rgba(73, 204, 255, 85);
            }
            QLabel#brand {
                color: #f3fbff;
                font-size: 17px;
                font-weight: 800;
                padding: 13px;
                border: 1px solid rgba(73, 204, 255, 95);
                border-radius: 8px;
                background-color: rgba(16, 45, 72, 165);
            }
            QFrame#topBar, QFrame#glass, QFrame#metricTile, QFrame#chart, QFrame#orbitPanel, QFrame#orbitCard {
                background-color: rgba(8, 22, 38, 190);
                border: 1px solid rgba(89, 212, 255, 88);
                border-radius: 8px;
            }
            QLabel#topTitle {
                color: #ffffff;
                font-size: 20px;
                font-weight: 800;
            }
            QLabel#statusPill {
                color: #dcf4ff;
                padding: 7px 10px;
                border: 1px solid rgba(90, 215, 255, 75);
                border-radius: 8px;
                background-color: rgba(10, 34, 56, 180);
                font-size: 12px;
            }
            QLabel#activeTask {
                color: #dff7ff;
                padding: 8px 12px;
                border-radius: 8px;
                border: 1px solid rgba(93, 220, 255, 82);
                background-color: rgba(7, 25, 43, 180);
                font-size: 13px;
                font-weight: 800;
            }
            QLabel#unreadBadge {
                min-width: 26px;
                min-height: 26px;
                padding: 2px 6px;
                border-radius: 8px;
                background-color: rgba(30, 98, 138, 190);
                border: 1px solid rgba(117, 228, 255, 135);
                color: #ffffff;
                font-weight: 900;
            }
            QLabel#unreadBadge[attention="true"] {
                background-color: rgba(0, 170, 255, 210);
            }
            QToolButton#navButton, QToolButton#collapseButton, QToolButton#roundTool {
                min-height: 46px;
                padding: 0 13px;
                border-radius: 8px;
                border: 1px solid rgba(90, 215, 255, 58);
                background-color: rgba(8, 24, 42, 120);
                color: #ceefff;
                font-weight: 700;
                font-size: 13px;
            }
            QToolButton#navButton:hover, QToolButton#collapseButton:hover, QToolButton#roundTool:hover {
                background-color: rgba(26, 116, 185, 150);
                border-color: rgba(134, 230, 255, 180);
            }
            QToolButton#navButton[active="true"] {
                background-color: rgba(0, 164, 255, 195);
                border-color: rgba(171, 239, 255, 225);
                color: #ffffff;
            }
            QLabel#metricTitle, QLabel#cardLabel {
                color: #a9dfff;
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#metricValue {
                color: #ffffff;
                font-size: 28px;
                font-weight: 850;
            }
            QLabel#sectionTitle {
                color: #ffffff;
                font-size: 17px;
                font-weight: 800;
            }
            QPushButton {
                min-height: 34px;
                padding: 0 16px;
                border-radius: 8px;
                border: 1px solid rgba(92, 217, 255, 110);
                background-color: rgba(0, 148, 255, 115);
                color: #f8fdff;
                font-weight: 800;
            }
            QPushButton:hover {
                background-color: rgba(0, 168, 255, 195);
            }
            QTextEdit#textPanel {
                background-color: rgba(3, 11, 20, 225);
                border: 1px solid rgba(89, 212, 255, 82);
                border-radius: 8px;
                color: #dff5ff;
                font-family: Consolas, "Cascadia Mono", monospace;
                font-size: 12px;
                padding: 12px;
            }
            QTextEdit#timelinePanel {
                background-color: rgba(3, 11, 20, 238);
                border: 1px solid rgba(89, 212, 255, 105);
                border-radius: 8px;
                color: #e6f8ff;
                font-family: Consolas, "Cascadia Mono", monospace;
                font-size: 12px;
                padding: 14px;
            }
            QLineEdit {
                min-height: 34px;
                border-radius: 8px;
                border: 1px solid rgba(89, 212, 255, 92);
                background-color: rgba(3, 11, 20, 225);
                color: #e9f7ff;
                padding: 0 12px;
            }
            QComboBox {
                min-height: 34px;
                border-radius: 8px;
                border: 1px solid rgba(89, 212, 255, 92);
                background-color: rgba(3, 11, 20, 225);
                color: #e9f7ff;
                padding: 0 10px;
            }
            QCheckBox#voiceCheck {
                color: #caedff;
                font-weight: 700;
                padding: 4px 0;
            }
            QSlider::groove:horizontal {
                height: 6px;
                border-radius: 3px;
                background: rgba(91, 218, 255, 65);
            }
            QSlider::handle:horizontal {
                width: 16px;
                margin: -6px 0;
                border-radius: 8px;
                background: #65dcff;
                border: 1px solid #d8fbff;
            }
            QScrollArea#scrollPage {
                border: 0;
                background: transparent;
            }
            QFrame#notificationPanel {
                background-color: rgba(3, 9, 17, 248);
                border-left: 1px solid rgba(89, 212, 255, 95);
            }
            QMainWindow[focusMode="true"] QFrame#sidebar,
            QMainWindow[focusMode="true"] QFrame#topBar,
            QMainWindow[focusMode="true"] QFrame#glass,
            QMainWindow[focusMode="true"] QFrame#metricTile,
            QMainWindow[focusMode="true"] QFrame#chart,
            QMainWindow[focusMode="true"] QFrame#orbitPanel,
            QMainWindow[focusMode="true"] QFrame#orbitCard {
                background-color: rgba(16, 5, 6, 220);
                border-color: rgba(255, 74, 92, 115);
            }
            QMainWindow[focusMode="true"] QLabel#activeTask,
            QMainWindow[focusMode="true"] QTextEdit#textPanel,
            QMainWindow[focusMode="true"] QTextEdit#timelinePanel,
            QMainWindow[focusMode="true"] QLineEdit,
            QMainWindow[focusMode="true"] QComboBox {
                background-color: rgba(12, 3, 4, 230);
                border-color: rgba(255, 74, 92, 130);
                color: #ffe9e9;
            }
            QMainWindow[focusMode="true"] QToolButton#navButton[active="true"],
            QMainWindow[focusMode="true"] QPushButton {
                background-color: rgba(150, 0, 18, 160);
                border-color: rgba(255, 95, 105, 190);
            }
            QMainWindow[focusMode="true"] QLabel#unreadBadge {
                background-color: rgba(150, 0, 18, 190);
                border-color: rgba(255, 95, 105, 190);
            }
            """
        )


class _ChatWorker(QThread):
    """Runs a chat request off the UI thread.

    AIRouter.chat() can block on a real network call to Gemini, and the UI
    thread must stay free so the IrisCore "thinking" animation keeps
    repainting while a reply is in flight. This worker only ever calls into
    DashboardViewModel.request_assistant_reply(), preserving the
    MainWindow -> DashboardViewModel -> AIRouter -> Provider call path.
    """

    completed = Signal(object)

    def __init__(self, view_model: DashboardViewModel, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._view_model = view_model

    def run(self) -> None:
        result = self._view_model.request_assistant_reply()
        self.completed.emit(result)


class MetricTile(QFrame):
    """Compact live metric tile."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("metricTile")
        self._shadow(QColor(49, 203, 255, 50))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        label = QLabel(title, self)
        label.setObjectName("metricTitle")
        self.value = QLabel("--", self)
        self.value.setObjectName("metricValue")
        self.value.setWordWrap(True)
        layout.addWidget(label)
        layout.addWidget(self.value)
        self.setMinimumHeight(112)

    def _shadow(self, color: QColor) -> None:
        effect = QGraphicsDropShadowEffect(self)
        effect.setBlurRadius(26)
        effect.setOffset(0, 0)
        effect.setColor(color)
        self.setGraphicsEffect(effect)


class OrbitCard(QFrame):
    """AI provider telemetry card."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("orbitCard")
        self._active = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        self.title = QLabel(title, self)
        self.title.setObjectName("sectionTitle")
        self.status = QLabel("Status: --", self)
        self.latency = QLabel("Latency: --", self)
        self.requests = QLabel("Requests: --", self)
        for label in (self.status, self.latency, self.requests):
            label.setObjectName("cardLabel")
        layout.addWidget(self.title)
        layout.addWidget(self.status)
        layout.addWidget(self.latency)
        layout.addWidget(self.requests)
        self.setMinimumHeight(140)

    def set_rows(self, status: str, latency: str, requests: str, active: bool = False) -> None:
        self._active = active
        self.status.setText(f"Status: {status}")
        self.latency.setText(f"Latency: {latency}")
        self.requests.setText(f"Requests: {requests}")
        self.update()

    def paintEvent(self, event: Any) -> None:
        super().paintEvent(event)
        if not self._active:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(98, 228, 255, 210), 2))
        painter.drawRoundedRect(self.rect().adjusted(2, 2, -2, -2), 8, 8)


class LiveChart(QFrame):
    """Real live chart with pyqtgraph when available."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("chart")
        self._values: deque[float] = deque([0.0] * 80, maxlen=80)
        self._target = 0.0
        self._curve: Any | None = None
        self._fallback: QLabel | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        label = QLabel(title, self)
        label.setObjectName("sectionTitle")
        layout.addWidget(label)
        if pg is not None:
            plot = pg.PlotWidget(self)
            plot.setBackground(None)
            plot.showGrid(x=False, y=True, alpha=0.15)
            plot.setYRange(0, 100)
            plot.hideAxis("bottom")
            plot.hideAxis("left")
            plot.setMouseEnabled(x=False, y=False)
            plot.setMenuEnabled(False)
            plot.setClipToView(True)
            self._curve = plot.plot(pen=pg.mkPen("#51d7ff", width=2), antialias=True)
            layout.addWidget(plot)
        else:
            self._fallback = QLabel("--", self)
            self._fallback.setObjectName("metricValue")
            self._fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(self._fallback, stretch=1)
        self.setMinimumHeight(185)

    def append(self, value: float) -> None:
        self._target = max(0.0, min(100.0, value))
        bounded = self._values[-1] + (self._target - self._values[-1]) * 0.34
        self._values.append(bounded)
        if self._curve is not None:
            self._curve.setData(list(self._values))
        if self._fallback is not None:
            self._fallback.setText(f"{bounded:.1f}%")

    def pulse(self) -> None:
        if abs(self._target - self._values[-1]) > 0.3:
            self.append(self._target)
        self.update()


class VoiceWaveform(QWidget):
    """Low-cost animated waveform for the future STT/TTS bridge."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._phase = 0.0
        self._state = "idle"
        self.setMinimumHeight(96)

    def set_phase(self, phase: float, state: str) -> None:
        self._phase = phase
        self._state = state
        self.update()

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(14, 10, -14, -10)
        color = QColor(255, 80, 94) if self._state == "error" else QColor(83, 219, 255)
        if self._state == "speaking":
            color = QColor(132, 242, 255)
        elif self._state == "listening":
            color = QColor(58, 232, 255)
        painter.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 95), 1))
        painter.drawRoundedRect(rect, 8, 8)
        bars = 38
        painter.setPen(QPen(color, 2.0))
        center_y = rect.center().y()
        for index in range(bars):
            x = rect.left() + 14 + index * ((rect.width() - 28) / max(1, bars - 1))
            active = 1.0 if self._state in {"listening", "speaking"} else 0.28
            height = 10 + active * 34 * abs(math.sin(self._phase * 2.2 + index * 0.42))
            painter.drawLine(int(x), int(center_y - height / 2), int(x), int(center_y + height / 2))


class IrisCoreWidget(QWidget):
    """Animated IRIS Core used as status, voice, workflow hub, and identity."""

    COLORS = {
        "idle": QColor(67, 198, 255),
        "listening": QColor(45, 224, 255),
        "thinking": QColor(178, 98, 255),
        "speaking": QColor(78, 234, 255),
        "workflow": QColor(48, 185, 255),
        "error": QColor(255, 74, 91),
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._phase = 0.0
        self._state = "idle"
        self._previous_state = "idle"
        self._transition_started = time.monotonic()
        self._volume = 0.45
        self._speech = ""
        self._speech_started = 0.0
        self._speech_duration = 3.4
        self._focus = False
        self.setMinimumSize(430, 430)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    @property
    def state(self) -> str:
        """Return the target visual state."""
        return self._state

    def set_phase(self, phase: float) -> None:
        self._phase = phase
        if self._state == "listening":
            self._volume = 0.35 + 0.45 * abs(math.sin(phase * 1.8))
        self.update()

    def set_state(self, state: str) -> None:
        if state in self.COLORS and state != self._state:
            self._previous_state = self._state
            self._state = state
            self._transition_started = time.monotonic()
            self.update()

    def set_volume(self, volume: float) -> None:
        self._volume = max(0.0, min(1.0, volume))
        if self._state != "listening":
            self.set_state("listening")

    def set_focus(self, focus: bool) -> None:
        if focus != self._focus:
            self._focus = focus
            self.update()

    def set_speech(self, text: str) -> None:
        self._speech = text
        self._speech_started = time.monotonic()
        self.set_state("speaking")
        QTimer.singleShot(int(self._speech_duration * 1000), self._clear_speech)

    def _clear_speech(self) -> None:
        self._speech = ""
        if self._state == "speaking":
            self._state = "idle"
        self.update()

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        center = QPointF(rect.center())
        radius = min(rect.width(), rect.height()) * 0.27
        color = self._current_color()
        breath = 1.0 + math.sin(self._phase * 1.5) * 0.045

        for index in range(5, 0, -1):
            alpha = 18 + index * 10
            painter.setPen(Qt.PenStyle.NoPen)
            glow = QColor(color)
            glow.setAlpha(alpha)
            painter.setBrush(glow)
            state_boost = self._volume * 18 if self._state == "listening" else 0
            r = radius * breath + index * 18 + state_boost
            painter.drawEllipse(center, r, r)

        painter.setBrush(QColor(4, 15, 27, 235))
        painter.setPen(QPen(color, 2.2))
        painter.drawEllipse(center, radius * breath, radius * breath)
        painter.setPen(QPen(QColor(236, 250, 255), 1.2))
        painter.drawEllipse(center, radius * 0.72, radius * 0.72)

        if self._state in {"thinking", "workflow"}:
            for index in range(18):
                angle = self._phase * 1.5 + index * math.tau / 18
                rr = radius * (0.92 + 0.18 * math.sin(self._phase + index))
                point = QPointF(center.x() + math.cos(angle) * rr, center.y() + math.sin(angle) * rr)
                painter.setBrush(QColor(color.red(), color.green(), color.blue(), 190))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(point, 3.5, 3.5)

        if self._state == "listening":
            for index in range(3):
                r = radius * (1.15 + self._volume * 0.35 + ((self._phase * .55 + index * .3) % 1.0))
                ring = QColor(color)
                ring.setAlpha(90 - index * 22)
                painter.setPen(QPen(ring, 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(center, r, r)

        if self._state == "speaking":
            for index in range(4):
                r = radius * (1.0 + ((self._phase * .42 + index * .21) % 1.0))
                ring = QColor(color)
                ring.setAlpha(95 - index * 18)
                painter.setPen(QPen(ring, 1.8))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(center, r, r)

        if self._state == "error":
            pulse = abs(math.sin(self._phase * 3.0))
            painter.setPen(QPen(QColor(255, 74, 91, int(160 * pulse)), 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(center, radius * (1.08 + pulse * 0.1), radius * (1.08 + pulse * 0.1))

        painter.setPen(QColor(255, 255, 255))
        font = QFont("Segoe UI", 28, QFont.Weight.Black)
        painter.setFont(font)
        painter.drawText(QRectF(center.x() - radius, center.y() - 38, radius * 2, 42), Qt.AlignmentFlag.AlignCenter, "IRIS")
        painter.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        painter.setPen(QColor(182, 229, 255))
        painter.drawText(QRectF(center.x() - radius, center.y() + 5, radius * 2, 42), Qt.AlignmentFlag.AlignCenter, "AI Operating System")

        if self._speech:
            self._draw_speech_cloud(painter, center, radius, color)

    FOCUS_COLOR = QColor(220, 38, 55)

    def _current_color(self) -> QColor:
        elapsed = min(1.0, (time.monotonic() - self._transition_started) / 0.38)
        ease = 1.0 - (1.0 - elapsed) ** 3
        start = self.COLORS[self._previous_state]
        end = self.COLORS[self._state]
        color = QColor(
            int(start.red() + (end.red() - start.red()) * ease),
            int(start.green() + (end.green() - start.green()) * ease),
            int(start.blue() + (end.blue() - start.blue()) * ease),
        )
        if not self._focus:
            return color
        focus_color = self.FOCUS_COLOR
        return QColor(
            int(color.red() * 0.35 + focus_color.red() * 0.65),
            int(color.green() * 0.35 + focus_color.green() * 0.65),
            int(color.blue() * 0.35 + focus_color.blue() * 0.65),
        )

    def _draw_speech_cloud(self, painter: QPainter, center: QPointF, radius: float, color: QColor) -> None:
        elapsed = time.monotonic() - self._speech_started
        if elapsed <= 0.28:
            opacity = elapsed / 0.28
        elif elapsed >= self._speech_duration - 0.55:
            opacity = max(0.0, (self._speech_duration - elapsed) / 0.55)
        else:
            opacity = 1.0
        width = min(self.width() * 0.58, 360)
        scale = 0.82 + 0.18 * opacity
        cloud = QRectF(center.x() - (width * scale) / 2, center.y() - radius - 108, width * scale, 86 * scale)
        painter.setOpacity(opacity)
        painter.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 180), 1.5))
        painter.setBrush(QColor(6, 22, 36, 225))
        painter.drawRoundedRect(cloud, 8, 8)
        painter.setPen(QColor(234, 251, 255))
        painter.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
        painter.drawText(cloud.adjusted(16, 10, -16, -34), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._speech)
        base_y = cloud.bottom() - 20
        painter.setPen(QPen(color, 2))
        for index in range(26):
            x = cloud.left() + 18 + index * ((cloud.width() - 36) / 26)
            height = 7 + 14 * abs(math.sin(self._phase * 2 + index * .55))
            painter.drawLine(int(x), int(base_y - height / 2), int(x), int(base_y + height / 2))
        painter.setOpacity(1.0)


class WorkflowGraph(QWidget):
    """Animated workflow route visualization."""

    NODES = ("Research", "Decision", "Workflow", "Studio", "Telegram", "Completed")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._phase = 0.0
        self.setMinimumHeight(520)

    def set_phase(self, phase: float) -> None:
        self._phase = phase
        self.update()

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(28, 28, -28, -28)
        x = rect.center().x()
        gap = rect.height() / max(1, len(self.NODES) - 1)
        centers = []
        for index, node in enumerate(self.NODES):
            y = rect.top() + index * gap
            node_rect = QRectF(x - 135, y - 28, 270, 56)
            painter.setPen(QPen(QColor(103, 219, 255, 170), 1.4))
            painter.setBrush(QColor(7, 27, 46, 215))
            painter.drawRoundedRect(node_rect, 8, 8)
            painter.setPen(QColor(238, 251, 255))
            painter.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
            painter.drawText(node_rect, Qt.AlignmentFlag.AlignCenter, node)
            centers.append(QPointF(x, y))
        for index in range(len(centers) - 1):
            start = centers[index]
            end = centers[index + 1]
            painter.setPen(QPen(QColor(76, 200, 255, 125), 2))
            painter.drawLine(start, end)
            progress = (self._phase * 0.45 + index * 0.16) % 1.0
            dot = QPointF(start.x(), start.y() + (end.y() - start.y()) * progress)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(146, 236, 255, 230))
            painter.drawEllipse(dot, 6, 6)


class NeuralBackground(QWidget):
    """Subtle animated neural grid background."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._phase = 0.0
        self._focus = False

    def set_phase(self, phase: float, focus: bool) -> None:
        self._phase = phase
        self._focus = focus
        self.update()

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        base = QColor(3, 7, 13) if not self._focus else QColor(5, 2, 2)
        accent = QColor(42, 190, 255) if not self._focus else QColor(220, 38, 55)
        painter.fillRect(self.rect(), base)
        pen = QPen(QColor(accent.red(), accent.green(), accent.blue(), 28), 1)
        painter.setPen(pen)
        step = 42
        offset = int((self._phase * 8) % step)
        for x in range(-step + offset, self.width(), step):
            painter.drawLine(x, 0, x, self.height())
        for y in range(-step + offset, self.height(), step):
            painter.drawLine(0, y, self.width(), y)
        painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 58), 1))
        points = []
        for index in range(36):
            x = (index * 97 + math.sin(self._phase + index) * 28) % max(1, self.width())
            y = (index * 53 + math.cos(self._phase * .8 + index) * 22) % max(1, self.height())
            points.append(QPointF(x, y))
            painter.drawEllipse(QPointF(x, y), 2.2, 2.2)
        for index, point in enumerate(points):
            other = points[(index * 7 + 5) % len(points)]
            if abs(point.x() - other.x()) + abs(point.y() - other.y()) < 390:
                painter.drawLine(point, other)
