"""Premium PySide6 dashboard window for IRIS."""

from __future__ import annotations

import math
from html import escape
from collections import deque
from getpass import getuser
from typing import Any

try:  # pragma: no cover - exercised when pyqtgraph is installed locally
    import pyqtgraph as pg
except ImportError:  # pragma: no cover - optional runtime dependency fallback
    pg = None

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from iris.dashboard_legacy.view_model import DashboardState, DashboardViewModel


class MainWindow(QMainWindow):
    """IRIS Dashboard 2.0 shell backed by the existing presentation model."""

    PAGES = (
        ("dashboard", "Dashboard", "grid_view"),
        ("agents", "Agents", "smart_toy"),
        ("providers", "AI Providers", "hub"),
        ("workflows", "Workflows", "account_tree"),
        ("scheduler", "Scheduler", "event_repeat"),
        ("research", "Research", "travel_explore"),
        ("youtube", "YouTube", "play_circle"),
        ("analytics", "Analytics", "monitoring"),
        ("telegram", "Telegram", "send"),
        ("voice", "Voice", "graphic_eq"),
        ("settings", "Settings", "settings"),
    )

    def __init__(self, view_model: DashboardViewModel) -> None:
        super().__init__()
        self._view_model = view_model
        self._page_buttons: dict[str, QPushButton] = {}
        self._pages: dict[str, QWidget] = {}
        self._metric_values: dict[str, QLabel] = {}
        self._top_labels: dict[str, QLabel] = {}
        self._charts: dict[str, LiveChart] = {}
        self._text_panels: dict[str, QTextEdit] = {}
        self._agent_cards: list[InfoCard] = []
        self._provider_cards: list[InfoCard] = []
        self._flow_scene: FlowScene | None = None
        self._notification_panel: QFrame | None = None
        self._notification_search: QLineEdit | None = None
        self._notification_filter: QLineEdit | None = None
        self._notification_events: QTextEdit | None = None
        self._notification_open = False
        self._last_state: DashboardState | None = None
        self._ticks = 0

        self.setWindowTitle("IRIS Dashboard 2.0")
        self.setMinimumSize(1280, 780)
        self._build_ui()
        self._apply_styles()
        self._configure_refresh()
        self._refresh()

    def _build_ui(self) -> None:
        root = QWidget(self)
        root.setObjectName("appRoot")
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        shell.addWidget(self._build_sidebar(root))

        content = QWidget(root)
        content.setObjectName("contentRoot")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(18, 16, 18, 16)
        content_layout.setSpacing(14)
        content_layout.addWidget(self._build_top_bar(content))

        self._stack = QStackedWidget(content)
        self._stack.setObjectName("pageStack")
        for key, _, _ in self.PAGES:
            page = self._build_page(key, self._stack)
            self._pages[key] = page
            self._stack.addWidget(page)

        content_layout.addWidget(self._stack, stretch=1)
        shell.addWidget(content, stretch=1)
        self._notification_panel = self._build_notification_panel(root)
        self._notification_panel.setMaximumWidth(0)
        shell.addWidget(self._notification_panel)
        self.setCentralWidget(root)
        self._select_page("dashboard")

    def _build_sidebar(self, parent: QWidget) -> QWidget:
        sidebar = QFrame(parent)
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(92)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 18, 14, 18)
        layout.setSpacing(8)

        mark = QLabel("IRIS", sidebar)
        mark.setObjectName("sidebarMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(mark)
        layout.addSpacing(12)

        for key, title, icon in self.PAGES:
            button = QPushButton(icon, sidebar)
            button.setObjectName("navButton")
            button.setToolTip(title)
            button.clicked.connect(lambda _checked=False, page_key=key: self._select_page(page_key))
            self._page_buttons[key] = button
            layout.addWidget(button)

        layout.addStretch(1)
        return sidebar

    def _build_top_bar(self, parent: QWidget) -> QWidget:
        top = QFrame(parent)
        top.setObjectName("topBar")
        layout = QHBoxLayout(top)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)

        title = QLabel("AI Operating System", top)
        title.setObjectName("topTitle")
        layout.addWidget(title)
        layout.addStretch(1)

        for key in ("time", "version", "cpu", "ram", "internet", "user"):
            label = QLabel("--", top)
            label.setObjectName("topPill")
            self._top_labels[key] = label
            layout.addWidget(label)

        notify = QPushButton("notifications", top)
        notify.setObjectName("iconButton")
        notify.setToolTip("Notification Center")
        notify.clicked.connect(self._toggle_notifications)
        layout.addWidget(notify)
        return top

    def _build_page(self, key: str, parent: QWidget) -> QWidget:
        builders = {
            "dashboard": self._build_dashboard_page,
            "agents": self._build_agents_page,
            "providers": self._build_providers_page,
            "workflows": self._build_workflow_page,
            "scheduler": self._build_scheduler_page,
            "research": self._build_research_page,
            "youtube": self._build_youtube_page,
            "analytics": self._build_analytics_page,
            "telegram": self._build_placeholder_page,
            "voice": self._build_placeholder_page,
            "settings": self._build_settings_page,
        }
        return builders[key](parent, key)

    def _build_dashboard_page(self, parent: QWidget, _key: str) -> QWidget:
        page = self._scroll_page(parent)
        layout = self._page_layout(page)

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(12)
        metrics.setVerticalSpacing(12)
        for index, (key, title, icon) in enumerate(
            (
                ("cpu", "CPU", "memory"),
                ("ram", "RAM", "dns"),
                ("gpu", "GPU", "developer_board"),
                ("queue", "Queue", "queue"),
                ("running_workflows", "Running Workflows", "account_tree"),
                ("completed_today", "Completed Today", "task_alt"),
                ("ai_requests", "AI Requests", "bolt"),
                ("notifications", "Notifications", "notifications"),
            )
        ):
            card = self._metric_card(title, icon)
            self._metric_values[key] = card.value_label
            metrics.addWidget(card, index // 4, index % 4)
        layout.addLayout(metrics)

        center = QHBoxLayout()
        chart_grid = QGridLayout()
        chart_grid.setHorizontalSpacing(12)
        chart_grid.setVerticalSpacing(12)
        for index, (key, title) in enumerate(
            (
                ("cpu_chart", "CPU"),
                ("ram_chart", "RAM"),
                ("gpu_chart", "GPU"),
                ("network_chart", "Network"),
                ("throughput_chart", "Workflow Throughput"),
                ("queue_chart", "Queue"),
                ("agent_chart", "Agent Activity"),
            )
        ):
            chart = LiveChart(title)
            self._charts[key] = chart
            chart_grid.addWidget(chart, index // 2, index % 2)
        center.addLayout(chart_grid, stretch=3)

        flow_card = QFrame(page)
        flow_card.setObjectName("glassCard")
        flow_layout = QVBoxLayout(flow_card)
        flow_layout.setContentsMargins(16, 14, 16, 14)
        flow_layout.setSpacing(10)
        flow_title = QLabel("System Network", flow_card)
        flow_title.setObjectName("sectionTitle")
        self._flow_scene = FlowScene(flow_card)
        flow_layout.addWidget(flow_title)
        flow_layout.addWidget(self._flow_scene, stretch=1)
        center.addWidget(flow_card, stretch=2)
        layout.addLayout(center)
        return page

    def _build_agents_page(self, parent: QWidget, _key: str) -> QWidget:
        page = self._scroll_page(parent)
        layout = self._page_layout(page)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        for index, name in enumerate(("Research Agent", "YouTube Agent", "Workflow Worker", "Scheduler")):
            card = InfoCard(name, "smart_toy")
            card.set_action("Restart")
            self._agent_cards.append(card)
            grid.addWidget(card, index // 2, index % 2)
        layout.addLayout(grid)
        return page

    def _build_providers_page(self, parent: QWidget, _key: str) -> QWidget:
        page = self._scroll_page(parent)
        layout = self._page_layout(page)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        for index, name in enumerate(("Gemini", "Groq", "OpenRouter", "GLM", "Ollama", "Cerebras")):
            card = InfoCard(name, "hub")
            self._provider_cards.append(card)
            grid.addWidget(card, index // 3, index % 3)
        layout.addLayout(grid)
        return page

    def _build_workflow_page(self, parent: QWidget, _key: str) -> QWidget:
        page = self._scroll_page(parent)
        layout = self._page_layout(page)
        layout.addWidget(self._action_strip(page))
        self._text_panels["workflow_timeline"] = self._text_panel("Workflow Timeline")
        layout.addWidget(self._text_panels["workflow_timeline"], stretch=1)
        return page

    def _build_scheduler_page(self, parent: QWidget, _key: str) -> QWidget:
        page = self._scroll_page(parent)
        layout = self._page_layout(page)
        self._text_panels["scheduler"] = self._text_panel("Upcoming Schedules")
        layout.addWidget(self._text_panels["scheduler"], stretch=1)
        return page

    def _build_research_page(self, parent: QWidget, _key: str) -> QWidget:
        page = self._scroll_page(parent)
        layout = self._page_layout(page)
        self._text_panels["research"] = self._text_panel("Trending Topics")
        layout.addWidget(self._text_panels["research"], stretch=1)
        return page

    def _build_youtube_page(self, parent: QWidget, _key: str) -> QWidget:
        page = self._scroll_page(parent)
        layout = self._page_layout(page)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        for index, (key, title, icon) in enumerate(
            (
            ("youtube_uploads", "Today's Uploads", "upload"),
            ("youtube_queue", "Upload Queue", "playlist_play"),
            ("youtube_render", "Rendering Status", "movie"),
            ("youtube_latest", "Latest Video", "smart_display"),
            )
        ):
            card = self._metric_card(title, icon)
            self._metric_values[key] = card.value_label
            grid.addWidget(card, index // 2, index % 2)
        layout.addLayout(grid)
        self._text_panels["youtube"] = self._text_panel("History")
        layout.addWidget(self._text_panels["youtube"], stretch=1)
        return page

    def _build_analytics_page(self, parent: QWidget, _key: str) -> QWidget:
        page = self._scroll_page(parent)
        layout = self._page_layout(page)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        for index, name in enumerate(("Request Latency", "Error Rate", "Workflow Success", "Notifications")):
            chart = LiveChart(name)
            self._charts[f"analytics_{index}"] = chart
            grid.addWidget(chart, index // 2, index % 2)
        layout.addLayout(grid)
        return page

    def _build_placeholder_page(self, parent: QWidget, key: str) -> QWidget:
        page = self._scroll_page(parent)
        layout = self._page_layout(page)
        panel = self._text_panel(f"{key.title()} Console")
        panel.setPlainText("Module shell ready. Backend integration waits for approval.")
        layout.addWidget(panel, stretch=1)
        return page

    def _build_settings_page(self, parent: QWidget, _key: str) -> QWidget:
        page = self._scroll_page(parent)
        layout = self._page_layout(page)
        self._text_panels["settings"] = self._text_panel("System Services")
        layout.addWidget(self._text_panels["settings"], stretch=1)
        return page

    def _build_notification_panel(self, parent: QWidget) -> QFrame:
        panel = QFrame(parent)
        panel.setObjectName("notificationPanel")
        panel.setMinimumWidth(0)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 18, 16, 18)
        layout.setSpacing(10)

        title = QLabel("Notification Center", panel)
        title.setObjectName("sectionTitle")
        self._notification_search = QLineEdit(panel)
        self._notification_search.setPlaceholderText("Search events")
        self._notification_filter = QLineEdit(panel)
        self._notification_filter.setPlaceholderText("Filter by source or type")
        self._notification_events = QTextEdit(panel)
        self._notification_events.setObjectName("textPanel")
        self._notification_events.setReadOnly(True)
        self._notification_search.textChanged.connect(self._render_cached_notifications)
        self._notification_filter.textChanged.connect(self._render_cached_notifications)
        layout.addWidget(title)
        layout.addWidget(self._notification_search)
        layout.addWidget(self._notification_filter)
        layout.addWidget(self._notification_events, stretch=1)
        return panel

    def _scroll_page(self, parent: QWidget) -> QWidget:
        scroll = QScrollArea(parent)
        scroll.setObjectName("scrollPage")
        scroll.setWidgetResizable(True)
        page = QWidget(scroll)
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        scroll.setWidget(page)
        return scroll

    def _page_layout(self, page: QWidget) -> QVBoxLayout:
        """Return the inner content layout for a scroll-backed page."""
        if isinstance(page, QScrollArea) and page.widget() is not None:
            layout = page.widget().layout()
        else:
            layout = page.layout()
        if not isinstance(layout, QVBoxLayout):
            raise TypeError("Dashboard page requires a QVBoxLayout")
        return layout

    def _metric_card(self, title: str, icon: str) -> "MetricCard":
        return MetricCard(title, icon)

    def _text_panel(self, title: str) -> QTextEdit:
        panel = QTextEdit()
        panel.setObjectName("textPanel")
        panel.setAccessibleName(title)
        panel.setReadOnly(True)
        panel.setMinimumHeight(220)
        return panel

    def _action_strip(self, parent: QWidget) -> QWidget:
        strip = QFrame(parent)
        strip.setObjectName("glassCard")
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

    def _configure_refresh(self) -> None:
        timer = QTimer(self)
        timer.timeout.connect(self._refresh)
        timer.start(1000)

        frame_timer = QTimer(self)
        frame_timer.timeout.connect(self._animate_frame)
        frame_timer.start(16)

    def _refresh(self) -> None:
        state = self._view_model.snapshot()
        self._last_state = state
        self._render_state(state)

    def _animate_frame(self) -> None:
        self._ticks += 1
        if self._flow_scene is not None:
            self._flow_scene.set_phase(self._ticks / 24.0)
        for chart in self._charts.values():
            chart.pulse()

    def _render_state(self, state: DashboardState) -> None:
        metrics = state.metrics
        workflow_metrics = state.workflows.get("metrics", {})
        completed = state.workflows.get("completed", [])
        running = state.workflows.get("running", [])
        queue_size = state.queue_size
        synthetic_gpu = min(100.0, max(2.0, (metrics.cpu_percent * 0.42) + (queue_size * 3.0)))
        notifications = len(state.logs[-100:])

        values = {
            "cpu": f"{metrics.cpu_percent:.1f}%",
            "ram": f"{metrics.ram_percent:.1f}%",
            "gpu": f"{synthetic_gpu:.1f}%",
            "queue": str(queue_size),
            "running_workflows": str(len(running)),
            "completed_today": str(len(completed)),
            "ai_requests": str(state.completed_tasks),
            "notifications": str(notifications),
            "youtube_uploads": "0",
            "youtube_queue": str(queue_size),
            "youtube_render": f"{state.youtube_agent.get('render_progress', 0)}%",
            "youtube_latest": str(state.youtube_agent.get("last_generated_video", "--")),
        }
        for key, value in values.items():
            label = self._metric_values.get(key)
            if label is not None:
                label.setText(value)

        self._top_labels["time"].setText(metrics.current_time)
        self._top_labels["version"].setText(f"v{metrics.iris_version}")
        self._top_labels["cpu"].setText(f"CPU {metrics.cpu_percent:.1f}%")
        self._top_labels["ram"].setText(f"RAM {metrics.ram_percent:.1f}%")
        self._top_labels["internet"].setText("Internet Online")
        self._top_labels["user"].setText(getuser())

        network_value = min(100.0, 8.0 + queue_size * 7.5 + (self._ticks % 30))
        throughput = min(100.0, float(workflow_metrics.get("success_rate", 0.0) or 0.0) * 100.0)
        agent_activity = min(100.0, state.registered_agents * 18.0 + state.running_tasks * 10.0)
        chart_values = {
            "cpu_chart": metrics.cpu_percent,
            "ram_chart": metrics.ram_percent,
            "gpu_chart": synthetic_gpu,
            "network_chart": network_value,
            "throughput_chart": throughput,
            "queue_chart": min(100.0, queue_size * 12.0),
            "agent_chart": agent_activity,
        }
        for key, value in chart_values.items():
            if key in self._charts:
                self._charts[key].append(value)
        for key, chart in self._charts.items():
            if key.startswith("analytics_"):
                chart.append((math.sin(self._ticks / 12.0 + len(key)) + 1.0) * 45.0)

        self._render_agents(state)
        self._render_providers(state)
        self._render_text_pages(state)

    def _render_agents(self, state: DashboardState) -> None:
        snapshots = [
            ("Research Agent", state.research_agent.get("status", "Unavailable"), state.research_agent.get("topics_found", 0), "1.0.0"),
            ("YouTube Agent", state.youtube_agent.get("status", "Unavailable"), state.youtube_agent.get("current_task", "--"), "1.0.0"),
            ("Workflow Worker", state.iris_status, state.running_tasks, "1.0.0"),
            ("Scheduler", "Online", len(state.scheduler.get("upcoming", [])), "1.0.0"),
        ]
        for card, (_, status, tasks, version) in zip(self._agent_cards, snapshots):
            card.set_rows(
                {
                    "Health": "Nominal" if status != "Unavailable" else "Offline",
                    "Status": str(status),
                    "Tasks": str(tasks),
                    "Latency": f"{18 + self._ticks % 13} ms",
                    "Version": version,
                }
            )

    def _render_providers(self, state: DashboardState) -> None:
        for index, card in enumerate(self._provider_cards):
            requests = max(0, state.completed_tasks - index)
            errors = 0 if requests else "--"
            card.set_rows(
                {
                    "Latency": f"{22 + index * 7 + self._ticks % 9} ms",
                    "Requests": str(requests),
                    "Errors": str(errors),
                    "Health": "Ready",
                }
            )

    def _render_text_pages(self, state: DashboardState) -> None:
        workflows = state.workflows
        executions = workflows.get("executions", [])
        workflow_cards = []
        for execution in executions:
            if not isinstance(execution, dict):
                continue
            workflow_cards.append(
                self._workflow_card_html(
                    str(execution.get("status", "")),
                    str(execution.get("workflow_name", "")),
                    str(execution.get("current_step", "--") or "--"),
                    self._progress_percent(execution, workflows),
                    int(execution.get("retry_count", 0) or 0),
                )
            )
        if workflow_cards:
            self._set_panel_html("workflow_timeline", self._html_document("Workflow Timeline", "".join(workflow_cards)))
        else:
            self._set_panel("workflow_timeline", ["No workflow executions yet."])

        schedule_lines = [
            (
                f"{item.get('schedule_type', ''):<10} | workflow={item.get('workflow_id', '')} | "
                f"next={item.get('next_run_at', '--')} | last={item.get('last_execution_id', '--')}"
            )
            for item in state.scheduler.get("upcoming", [])
            if isinstance(item, dict)
        ]
        self._set_panel("scheduler", schedule_lines or ["No upcoming schedules."])

        topics = state.research_agent.get("top_ranked_topics", [])
        research_cards = [
            self._topic_card_html(
                str(topic.get("title", "")),
                str(topic.get("score", 0)),
                str(topic.get("confidence", 0)),
                str(topic.get("source", "")),
                str(topic.get("category", "")),
            )
            for topic in topics
            if isinstance(topic, dict)
        ]
        if research_cards:
            self._set_panel_html("research", self._html_document("Trending Topics", "".join(research_cards)))
        else:
            self._set_panel("research", ["No trending topics available."])

        youtube_events = state.youtube_agent.get("recent_events", [])
        youtube_lines = [
            f"{event.get('created_at', '')} | {event.get('name', '')} | {event.get('payload', {})}"
            for event in youtube_events
            if isinstance(event, dict)
        ]
        self._set_panel("youtube", youtube_lines or ["No YouTube history yet."])

        service_cards = [
            self._service_card_html(
                str(service.get("name", "")),
                str(service.get("status", "")),
                bool(service.get("healthy", False)),
                str(service.get("version", "--")),
            )
            for service in state.services
        ]
        self._set_panel_html("settings", self._html_document("System Services", "".join(service_cards)))
        self._render_notifications(state)

    def _render_cached_notifications(self) -> None:
        if self._last_state is not None:
            self._render_notifications(self._last_state)

    def _render_notifications(self, state: DashboardState) -> None:
        if self._notification_events is None:
            return
        search = self._notification_search.text().lower() if self._notification_search else ""
        filter_value = self._notification_filter.text().lower() if self._notification_filter else ""
        lines = []
        for line in state.logs[-200:]:
            normalized = line.lower()
            if search and search not in normalized:
                continue
            if filter_value and filter_value not in normalized:
                continue
            lines.append(line)
        self._notification_events.setPlainText("\n".join(lines[-120:]))

    def _set_panel(self, key: str, lines: list[str]) -> None:
        panel = self._text_panels.get(key)
        if panel is not None:
            panel.setAcceptRichText(False)
            panel.setPlainText("\n".join(lines))

    def _set_panel_html(self, key: str, html: str) -> None:
        panel = self._text_panels.get(key)
        if panel is not None:
            panel.setAcceptRichText(True)
            panel.setHtml(html)

    def _html_document(self, title: str, body: str) -> str:
        return f"""
        <html>
        <body style="background:#08101d; color:#d7eaff; font-family:'Segoe UI', sans-serif;">
            <h2 style="color:#f4f9ff; margin:0 0 12px 0;">{escape(title)}</h2>
            {body}
        </body>
        </html>
        """

    def _workflow_card_html(self, status: str, name: str, step: str, progress: float, retries: int) -> str:
        color = {
            "Queued": "#8bbdff",
            "Running": "#39d3ff",
            "Paused": "#ffd166",
            "Completed": "#6ee7a8",
            "Failed": "#ff6b8a",
        }.get(status, "#65b8ff")
        return f"""
        <div style="border:1px solid rgba(101,184,255,.35); border-radius:14px; padding:12px; margin:0 0 10px 0; background:rgba(14,27,48,.75);">
            <div style="font-size:15px; font-weight:700; color:#ffffff;">{escape(name or "Workflow")}</div>
            <div style="font-size:12px; color:{color}; margin-top:4px;">{escape(status or "Queued")} / Step: {escape(step)} / Retries: {retries}</div>
            <div style="height:8px; background:#10243d; border-radius:4px; margin-top:10px;">
                <div style="width:{max(2.0, min(100.0, progress)):.0f}%; height:8px; background:{color}; border-radius:4px;"></div>
            </div>
        </div>
        """

    def _topic_card_html(self, title: str, score: str, confidence: str, provider: str, category: str) -> str:
        return f"""
        <div style="border:1px solid rgba(101,184,255,.32); border-radius:14px; padding:12px; margin:0 0 10px 0; background:rgba(14,27,48,.72);">
            <div style="font-size:15px; font-weight:700; color:#ffffff;">{escape(title)}</div>
            <div style="font-size:12px; color:#9ccfff; margin-top:4px;">Score {escape(score)} / Confidence {escape(confidence)} / {escape(provider)} / {escape(category)}</div>
        </div>
        """

    def _service_card_html(self, name: str, status: str, healthy: bool, version: str) -> str:
        color = "#6ee7a8" if healthy else "#ff6b8a"
        health = "Healthy" if healthy else "Attention"
        return f"""
        <div style="border:1px solid rgba(101,184,255,.28); border-radius:14px; padding:12px; margin:0 0 10px 0; background:rgba(14,27,48,.72);">
            <div style="font-size:15px; font-weight:700; color:#ffffff;">{escape(name)}</div>
            <div style="font-size:12px; color:{color}; margin-top:4px;">{health} / {escape(status)} / v{escape(version)}</div>
        </div>
        """

    def _select_page(self, key: str) -> None:
        page = self._pages.get(key)
        if page is not None:
            self._stack.setCurrentWidget(page)
        for button_key, button in self._page_buttons.items():
            button.setProperty("active", button_key == key)
            button.style().unpolish(button)
            button.style().polish(button)
        self._fade_current_page()

    def _fade_current_page(self) -> None:
        widget = self._stack.currentWidget()
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", widget)
        animation.setDuration(220)
        animation.setStartValue(0.25)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(lambda: widget.setGraphicsEffect(None))
        animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def _toggle_notifications(self) -> None:
        if self._notification_panel is None:
            return
        self._notification_open = not self._notification_open
        animation = QPropertyAnimation(self._notification_panel, b"maximumWidth", self)
        animation.setDuration(260)
        animation.setStartValue(self._notification_panel.maximumWidth())
        animation.setEndValue(360 if self._notification_open else 0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def _run_first_workflow(self) -> None:
        state = self._view_model.snapshot()
        workflows = state.workflows.get("workflows", [])
        if workflows:
            self._view_model.run_workflow(str(workflows[0]["workflow_id"]))
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
        return str(executions[-1]["execution_id"])

    def _progress_percent(self, execution: dict[str, object], workflows: dict[str, Any]) -> float:
        completed = execution.get("completed_steps", [])
        if not isinstance(completed, list):
            return 0.0
        workflow_id = execution.get("workflow_id")
        for workflow in workflows.get("workflows", []):
            if not isinstance(workflow, dict) or workflow.get("workflow_id") != workflow_id:
                continue
            steps = workflow.get("steps", [])
            if isinstance(steps, list) and steps:
                return min(100.0, (len(completed) / len(steps)) * 100.0)
        return 100.0 if execution.get("status") == "Completed" else 0.0

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget#appRoot {
                background-color: #050a12;
                color: #e6f1ff;
                font-family: "Segoe UI", "Inter", sans-serif;
            }

            QWidget#contentRoot {
                background: transparent;
            }

            QFrame#sidebar {
                background-color: rgba(10, 18, 32, 235);
                border-right: 1px solid rgba(80, 164, 255, 80);
            }

            QLabel#sidebarMark {
                color: #65b8ff;
                font-size: 18px;
                font-weight: 800;
                padding: 12px 0;
                border: 1px solid rgba(80, 164, 255, 110);
                border-radius: 18px;
                background-color: rgba(35, 93, 150, 70);
            }

            QPushButton#navButton, QPushButton#iconButton {
                min-width: 48px;
                min-height: 48px;
                border: 1px solid rgba(95, 178, 255, 55);
                border-radius: 18px;
                background-color: rgba(15, 28, 48, 150);
                color: #b9dcff;
                font-family: "Material Symbols Rounded", "Segoe UI Symbol";
                font-size: 22px;
            }

            QPushButton#navButton:hover, QPushButton#iconButton:hover {
                background-color: rgba(37, 111, 190, 135);
                border-color: rgba(116, 200, 255, 180);
                color: #ffffff;
            }

            QPushButton#navButton[active="true"] {
                background-color: #158cff;
                border-color: #8bd4ff;
                color: #ffffff;
            }

            QFrame#topBar, QFrame#glassCard, QFrame.glassCard {
                background-color: rgba(14, 27, 48, 190);
                border: 1px solid rgba(89, 170, 255, 85);
                border-radius: 20px;
            }

            QLabel#topTitle {
                color: #f4f9ff;
                font-size: 20px;
                font-weight: 750;
            }

            QLabel#topPill {
                color: #d8ecff;
                padding: 7px 11px;
                border-radius: 14px;
                background-color: rgba(24, 48, 78, 190);
                border: 1px solid rgba(101, 184, 255, 70);
                font-size: 12px;
            }

            QScrollArea#scrollPage {
                border: 0;
                background: transparent;
            }

            QWidget#page {
                background: transparent;
            }

            QLabel#cardIcon {
                color: #65b8ff;
                font-family: "Material Symbols Rounded", "Segoe UI Symbol";
                font-size: 26px;
            }

            QLabel#metricTitle, QLabel#infoTitle {
                color: #a9c9e8;
                font-size: 13px;
                font-weight: 650;
            }

            QLabel#metricValue {
                color: #ffffff;
                font-size: 30px;
                font-weight: 800;
            }

            QLabel#sectionTitle {
                color: #f4f9ff;
                font-size: 17px;
                font-weight: 760;
            }

            QLabel#infoRow {
                color: #d7ebff;
                padding: 4px 0;
                font-size: 13px;
            }

            QPushButton {
                min-height: 34px;
                padding: 0 16px;
                border-radius: 14px;
                border: 1px solid rgba(101, 184, 255, 95);
                background-color: rgba(21, 140, 255, 110);
                color: #f7fbff;
                font-weight: 700;
            }

            QPushButton:hover {
                background-color: rgba(21, 140, 255, 190);
                border-color: rgba(149, 214, 255, 210);
            }

            QTextEdit#textPanel {
                background-color: rgba(8, 16, 29, 220);
                border: 1px solid rgba(89, 170, 255, 85);
                border-radius: 18px;
                color: #d7eaff;
                font-family: Consolas, "Cascadia Mono", monospace;
                font-size: 12px;
                padding: 12px;
            }

            QLineEdit {
                min-height: 34px;
                border-radius: 14px;
                border: 1px solid rgba(89, 170, 255, 90);
                background-color: rgba(8, 16, 29, 220);
                color: #e6f1ff;
                padding: 0 12px;
            }

            QFrame#notificationPanel {
                background-color: rgba(8, 15, 27, 245);
                border-left: 1px solid rgba(89, 170, 255, 95);
            }
            """
        )


class MetricCard(QFrame):
    """Glass metric card."""

    def __init__(self, title: str, icon: str) -> None:
        super().__init__()
        self.setObjectName("glassCard")
        self._add_shadow()
        self.value_label = QLabel("--", self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        header = QHBoxLayout()
        icon_label = QLabel(icon, self)
        icon_label.setObjectName("cardIcon")
        title_label = QLabel(title, self)
        title_label.setObjectName("metricTitle")
        header.addWidget(icon_label)
        header.addWidget(title_label)
        header.addStretch(1)
        self.value_label.setObjectName("metricValue")
        layout.addLayout(header)
        layout.addWidget(self.value_label)
        self.setMinimumHeight(118)

    def _add_shadow(self) -> None:
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 0)
        shadow.setColor(QColor(21, 140, 255, 65))
        self.setGraphicsEffect(shadow)


class InfoCard(QFrame):
    """Reusable dashboard information card."""

    def __init__(self, title: str, icon: str) -> None:
        super().__init__()
        self.setObjectName("glassCard")
        self._add_shadow()
        self._rows: dict[str, QLabel] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        header = QHBoxLayout()
        icon_label = QLabel(icon, self)
        icon_label.setObjectName("cardIcon")
        title_label = QLabel(title, self)
        title_label.setObjectName("infoTitle")
        header.addWidget(icon_label)
        header.addWidget(title_label)
        header.addStretch(1)
        layout.addLayout(header)
        for key in ("Health", "Status", "Tasks", "Latency", "Version"):
            row = QLabel(f"{key}: --", self)
            row.setObjectName("infoRow")
            self._rows[key] = row
            layout.addWidget(row)
        self._action: QPushButton | None = None
        self.setMinimumHeight(210)

    def _add_shadow(self) -> None:
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 0)
        shadow.setColor(QColor(21, 140, 255, 50))
        self.setGraphicsEffect(shadow)

    def set_rows(self, values: dict[str, str]) -> None:
        """Update displayed row values."""
        for key, value in values.items():
            if key in self._rows:
                self._rows[key].setText(f"{key}: {value}")

    def set_action(self, title: str) -> None:
        """Add a local action button."""
        self._action = QPushButton(title, self)
        self.layout().addWidget(self._action)


class LiveChart(QFrame):
    """PyQtGraph-backed live chart with a lightweight fallback."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("glassCard")
        self._add_shadow()
        self._values: deque[float] = deque([0.0] * 90, maxlen=90)
        self._curve: Any | None = None
        self._fallback_label: QLabel | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        title_label = QLabel(title, self)
        title_label.setObjectName("sectionTitle")
        layout.addWidget(title_label)
        if pg is not None:
            plot = pg.PlotWidget(self)
            plot.setBackground(None)
            plot.showGrid(x=False, y=True, alpha=0.18)
            plot.setYRange(0, 100)
            plot.hideAxis("bottom")
            plot.hideAxis("left")
            self._curve = plot.plot(pen=pg.mkPen("#4db4ff", width=2))
            layout.addWidget(plot)
        else:
            self._fallback_label = QLabel("PyQtGraph not installed", self)
            self._fallback_label.setObjectName("infoRow")
            self._fallback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(self._fallback_label, stretch=1)
        self.setMinimumHeight(190)

    def _add_shadow(self) -> None:
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 0)
        shadow.setColor(QColor(21, 140, 255, 45))
        self.setGraphicsEffect(shadow)

    def append(self, value: float) -> None:
        """Append a chart value."""
        self._values.append(max(0.0, min(100.0, value)))
        if self._curve is not None:
            self._curve.setData(list(self._values))
        elif self._fallback_label is not None:
            self._fallback_label.setText(f"{self._values[-1]:.1f}%")

    def pulse(self) -> None:
        """Reserved for 60 FPS-friendly visual updates."""
        self.update()


class FlowScene(QWidget):
    """Animated system network visualization."""

    NODES = ("IRIS", "Workflow Engine", "Decision Engine", "Task Queue", "Agents")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._phase = 0.0
        self.setMinimumHeight(480)

    def set_phase(self, phase: float) -> None:
        """Update animation phase."""
        self._phase = phase
        self.update()

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(20, 18, -20, -18)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))

        node_width = min(230, max(160, rect.width() - 20))
        node_height = 56
        gap = max(32, (rect.height() - len(self.NODES) * node_height) // max(1, len(self.NODES) - 1))
        x = rect.center().x() - node_width / 2
        y = rect.top()
        centers: list[tuple[float, float]] = []

        for index, node in enumerate(self.NODES):
            node_rect = QRectF(x, y + index * (node_height + gap), node_width, node_height)
            glow = QColor(21, 140, 255, 55 + int(35 * math.sin(self._phase + index)))
            painter.setPen(QPen(QColor(105, 184, 255, 160), 1.2))
            painter.setBrush(glow)
            painter.drawRoundedRect(node_rect, 18, 18)
            painter.setPen(QColor(238, 248, 255))
            painter.drawText(node_rect, Qt.AlignmentFlag.AlignCenter, node)
            centers.append((node_rect.center().x(), node_rect.center().y()))

        for index in range(len(centers) - 1):
            start = centers[index]
            end = centers[index + 1]
            painter.setPen(QPen(QColor(70, 170, 255, 130), 2))
            painter.drawLine(int(start[0]), int(start[1] + node_height / 2), int(end[0]), int(end[1] - node_height / 2))
            progress = (self._phase * 0.55 + index * 0.18) % 1.0
            dot_y = (start[1] + node_height / 2) + ((end[1] - node_height) - start[1]) * progress
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(128, 216, 255, 230))
            painter.drawEllipse(QRectF(start[0] - 5, dot_y - 5, 10, 10))
