"""Main PySide6 dashboard window for IRIS."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from iris.dashboard.view_model import DashboardState, DashboardViewModel


class MainWindow(QMainWindow):
    """IRIS dashboard shell backed by a presentation model."""

    SERVICE_NAMES = (
        "Configuration",
        "Storage",
        "Secrets",
        "Process Manager",
        "Notifications",
        "Service Registry",
    )

    def __init__(self, view_model: DashboardViewModel) -> None:
        super().__init__()
        self._view_model = view_model
        self._metric_labels: dict[str, QLabel] = {}
        self._status_labels: dict[str, QLabel] = {}
        self._service_labels: dict[str, dict[str, QLabel]] = {}
        self._youtube_labels: dict[str, QLabel] = {}
        self._youtube_progress: dict[str, QProgressBar] = {}
        self._youtube_events: QTextEdit | None = None
        self._research_labels: dict[str, QLabel] = {}
        self._research_providers: QTextEdit | None = None
        self._research_topics: QTextEdit | None = None
        self._research_events: QTextEdit | None = None
        self._workflow_panels: dict[str, QTextEdit] = {}
        self._scheduler_panel: QTextEdit | None = None
        self._history_panel: QTextEdit | None = None
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

        tabs = QTabWidget(container)
        tabs.addTab(self._build_overview_tab(tabs), "Overview")
        tabs.addTab(self._build_services_tab(tabs), "System Services")
        tabs.addTab(self._build_workflows_tab(tabs), "Workflows")
        tabs.addTab(self._build_scheduler_tab(tabs), "Scheduler")
        tabs.addTab(self._build_history_tab(tabs), "Execution History")
        tabs.addTab(self._build_youtube_tab(tabs), "YouTube Agent")
        tabs.addTab(self._build_research_tab(tabs), "Research")

        layout.addWidget(tabs)
        container.setLayout(layout)
        self.setCentralWidget(container)
        self._build_status_bar()
        self._apply_styles()

    def _build_overview_tab(self, parent: QWidget) -> QWidget:
        """Build the operational overview tab."""
        tab = QWidget(parent)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        layout.addLayout(self._build_header(tab))
        layout.addLayout(self._build_metrics(tab))
        layout.addLayout(self._build_actions(tab))
        layout.addWidget(self._build_logs(tab), stretch=1)
        return tab

    def _build_services_tab(self, parent: QWidget) -> QWidget:
        """Build the system services tab."""
        tab = QWidget(parent)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        for name in self.SERVICE_NAMES:
            row = QWidget(tab)
            row.setObjectName("serviceRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(14, 12, 14, 12)
            row_layout.setSpacing(18)

            name_label = QLabel(name, row)
            name_label.setObjectName("serviceName")
            status_label = QLabel("Stopped", row)
            healthy_label = QLabel("Healthy: --", row)
            version_label = QLabel("Version: --", row)

            self._service_labels[name] = {
                "status": status_label,
                "healthy": healthy_label,
                "version": version_label,
            }

            row_layout.addWidget(name_label, stretch=2)
            row_layout.addWidget(status_label, stretch=1)
            row_layout.addWidget(healthy_label, stretch=1)
            row_layout.addWidget(version_label, stretch=1)
            layout.addWidget(row)

        layout.addStretch(1)
        return tab

    def _build_workflows_tab(self, parent: QWidget) -> QWidget:
        """Build the workflow operations tab."""
        tab = QWidget(parent)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        actions = QHBoxLayout()
        run_button = QPushButton("Run", tab)
        pause_button = QPushButton("Pause", tab)
        resume_button = QPushButton("Resume", tab)
        retry_button = QPushButton("Retry", tab)
        cancel_button = QPushButton("Cancel", tab)
        refresh_button = QPushButton("Refresh", tab)
        run_button.clicked.connect(self._run_first_workflow)
        pause_button.clicked.connect(self._pause_latest_execution)
        resume_button.clicked.connect(self._resume_latest_execution)
        retry_button.clicked.connect(self._retry_latest_execution)
        cancel_button.clicked.connect(self._cancel_latest_execution)
        refresh_button.clicked.connect(self._refresh)
        for button in (run_button, pause_button, resume_button, retry_button, cancel_button, refresh_button):
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self._workflow_panels["summary"] = self._research_panel(tab, "Workflow Details")
        layout.addWidget(self._labeled_panel(tab, "Workflow Details", self._workflow_panels["summary"]), stretch=1)
        return tab

    def _build_scheduler_tab(self, parent: QWidget) -> QWidget:
        """Build the scheduler tab."""
        tab = QWidget(parent)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        refresh_button = QPushButton("Refresh", tab)
        refresh_button.clicked.connect(self._refresh)
        layout.addWidget(refresh_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self._scheduler_panel = self._research_panel(tab, "Upcoming Schedules")
        layout.addWidget(self._labeled_panel(tab, "Upcoming Schedules", self._scheduler_panel), stretch=1)
        return tab

    def _build_history_tab(self, parent: QWidget) -> QWidget:
        """Build the workflow execution history tab."""
        tab = QWidget(parent)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self._history_panel = self._research_panel(tab, "Execution History")
        layout.addWidget(self._labeled_panel(tab, "Execution History", self._history_panel), stretch=1)
        return tab

    def _build_youtube_tab(self, parent: QWidget) -> QWidget:
        """Build the YouTube Agent operational tab."""
        tab = QWidget(parent)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        for key, title in (
            ("status", "Current Status"),
            ("current_task", "Current Task"),
            ("clip_pilot_process_state", "ClipPilot Process State"),
            ("last_generated_video", "Last Generated Video"),
            ("last_upload_url", "Last Upload URL"),
        ):
            row = self._youtube_row(tab, title)
            self._youtube_labels[key] = row.findChild(QLabel, "youtubeValue")
            layout.addWidget(row)

        layout.addWidget(self._youtube_progress_row(tab, "render_progress", "Render Progress"))
        layout.addWidget(self._youtube_progress_row(tab, "upload_progress", "Upload Progress"))

        label = QLabel("Recent Events", tab)
        label.setObjectName("sectionLabel")
        self._youtube_events = QTextEdit(tab)
        self._youtube_events.setObjectName("logPanel")
        self._youtube_events.setReadOnly(True)
        layout.addWidget(label)
        layout.addWidget(self._youtube_events, stretch=1)
        return tab

    def _build_research_tab(self, parent: QWidget) -> QWidget:
        """Build the Research Agent tab."""
        tab = QWidget(parent)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        layout.addLayout(self._build_research_actions(tab))

        for key, title in (
            ("status", "Current Status"),
            ("current_scan", "Current Scan"),
            ("topics_found", "Topics Found"),
            ("last_scan", "Last Scan"),
        ):
            row = self._research_row(tab, title)
            self._research_labels[key] = row.findChild(QLabel, "researchValue")
            layout.addWidget(row)

        panes = QGridLayout()
        panes.setHorizontalSpacing(12)
        panes.setVerticalSpacing(12)
        self._research_providers = self._research_panel(tab, "Providers")
        self._research_topics = self._research_panel(tab, "Top Ranked Topics")
        self._research_events = self._research_panel(tab, "Recent Events")
        panes.addWidget(self._labeled_panel(tab, "Providers", self._research_providers), 0, 0)
        panes.addWidget(self._labeled_panel(tab, "Top Ranked Topics", self._research_topics), 0, 1)
        panes.addWidget(self._labeled_panel(tab, "Recent Events", self._research_events), 1, 0, 1, 2)
        layout.addLayout(panes, stretch=1)
        return tab

    def _build_research_actions(self, parent: QWidget) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(10)

        run_button = QPushButton("Run Scan", parent)
        refresh_button = QPushButton("Refresh", parent)
        stop_button = QPushButton("Stop", parent)
        run_button.clicked.connect(self._request_research_scan)
        refresh_button.clicked.connect(self._refresh)
        stop_button.clicked.connect(self._request_research_stop)

        layout.addWidget(run_button)
        layout.addWidget(refresh_button)
        layout.addWidget(stop_button)
        layout.addStretch(1)
        return layout

    def _research_row(self, parent: QWidget, title: str) -> QWidget:
        row = QWidget(parent)
        row.setObjectName("serviceRow")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(14, 12, 14, 12)
        row_layout.setSpacing(18)

        name_label = QLabel(title, row)
        name_label.setObjectName("serviceName")
        value_label = QLabel("--", row)
        value_label.setObjectName("researchValue")
        value_label.setWordWrap(True)

        row_layout.addWidget(name_label, stretch=1)
        row_layout.addWidget(value_label, stretch=3)
        return row

    def _research_panel(self, parent: QWidget, name: str) -> QTextEdit:
        panel = QTextEdit(parent)
        panel.setObjectName("logPanel")
        panel.setAccessibleName(name)
        panel.setReadOnly(True)
        return panel

    def _labeled_panel(self, parent: QWidget, title: str, panel: QTextEdit) -> QWidget:
        section = QWidget(parent)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        label = QLabel(title, section)
        label.setObjectName("sectionLabel")
        layout.addWidget(label)
        layout.addWidget(panel)
        return section

    def _youtube_row(self, parent: QWidget, title: str) -> QWidget:
        row = QWidget(parent)
        row.setObjectName("serviceRow")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(14, 12, 14, 12)
        row_layout.setSpacing(18)

        name_label = QLabel(title, row)
        name_label.setObjectName("serviceName")
        value_label = QLabel("--", row)
        value_label.setObjectName("youtubeValue")
        value_label.setWordWrap(True)

        row_layout.addWidget(name_label, stretch=1)
        row_layout.addWidget(value_label, stretch=3)
        return row

    def _youtube_progress_row(self, parent: QWidget, key: str, title: str) -> QWidget:
        row = QWidget(parent)
        row.setObjectName("serviceRow")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(14, 12, 14, 12)
        row_layout.setSpacing(18)

        name_label = QLabel(title, row)
        name_label.setObjectName("serviceName")
        progress = QProgressBar(row)
        progress.setRange(0, 100)
        progress.setValue(0)
        progress.setTextVisible(True)
        self._youtube_progress[key] = progress

        row_layout.addWidget(name_label, stretch=1)
        row_layout.addWidget(progress, stretch=3)
        return row

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
            layout.addWidget(self._metric_card(parent, key, title), index // 4, index % 4)

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

        layout.addWidget(QPushButton("Start", parent))
        layout.addWidget(QPushButton("Stop", parent))
        layout.addWidget(QPushButton("Settings", parent))
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
        self._render_state(self._view_model.snapshot())

    def _request_research_scan(self) -> None:
        self._view_model.request_research_scan()
        self._refresh()

    def _request_research_stop(self) -> None:
        self._view_model.request_research_stop()
        self._refresh()

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

        for service in state.services:
            name = str(service["name"])
            labels = self._service_labels.get(name)
            if labels is None:
                continue

            labels["status"].setText(str(service["status"]))
            labels["healthy"].setText(f"Healthy: {service['healthy']}")
            labels["version"].setText(f"Version: {service['version']}")

        youtube = state.youtube_agent
        for key, label in self._youtube_labels.items():
            label.setText(str(youtube.get(key, "--")))

        for key, progress in self._youtube_progress.items():
            value = int(youtube.get(key, 0) or 0)
            progress.setValue(max(0, min(100, value)))

        if self._youtube_events is not None:
            event_lines = [
                f"{event.get('created_at', '')} | {event.get('name', '')} | {event.get('payload', {})}"
                for event in youtube.get("recent_events", [])
                if isinstance(event, dict)
            ]
            self._youtube_events.setPlainText("\n".join(event_lines[-100:]))

        research = state.research_agent
        for key, label in self._research_labels.items():
            label.setText(str(research.get(key, "--")))

        if self._research_providers is not None:
            provider_lines = [
                (
                    f"{provider.get('name', '')} | enabled={provider.get('enabled', False)} | "
                    f"healthy={provider.get('healthy', True)} | topics={provider.get('topics_found', 0)}"
                )
                for provider in research.get("providers", [])
                if isinstance(provider, dict)
            ]
            self._research_providers.setPlainText("\n".join(provider_lines))

        if self._research_topics is not None:
            topic_lines = [
                (
                    f"{index + 1}. {topic.get('title', '')} | score={topic.get('score', 0)} | "
                    f"source={topic.get('source', '')}"
                )
                for index, topic in enumerate(research.get("top_ranked_topics", []))
                if isinstance(topic, dict)
            ]
            self._research_topics.setPlainText("\n".join(topic_lines))

        if self._research_events is not None:
            research_event_lines = [
                f"{event.get('created_at', '')} | {event.get('name', '')} | {event.get('payload', {})}"
                for event in research.get("recent_events", [])
                if isinstance(event, dict)
            ]
            self._research_events.setPlainText("\n".join(research_event_lines[-100:]))

        self._render_workflow_state(state)

    def _render_workflow_state(self, state: DashboardState) -> None:
        workflows = state.workflows
        if "summary" in self._workflow_panels:
            lines = [
                (
                    f"{workflow.get('name', '')} | id={workflow.get('workflow_id', '')} | "
                    f"steps={len(workflow.get('steps', []))}"
                )
                for workflow in workflows.get("workflows", [])
                if isinstance(workflow, dict)
            ]
            metrics = workflows.get("metrics", {})
            lines.extend(
                [
                    "",
                    f"Running workflows: {len(workflows.get('running', []))}",
                    f"Queued workflows: {len(workflows.get('queued', []))}",
                    f"Completed workflows: {len(workflows.get('completed', []))}",
                    f"Failed workflows: {len(workflows.get('failed', []))}",
                    f"Success rate: {float(metrics.get('success_rate', 0.0)):.2%}" if isinstance(metrics, dict) else "",
                ]
            )
            self._workflow_panels["summary"].setPlainText("\n".join(lines))

        if self._scheduler_panel is not None:
            schedule_lines = [
                (
                    f"{schedule.get('schedule_type', '')} | workflow={schedule.get('workflow_id', '')} | "
                    f"next={schedule.get('next_run_at', '--')} | last={schedule.get('last_execution_id', '--')}"
                )
                for schedule in state.scheduler.get("upcoming", [])
                if isinstance(schedule, dict)
            ]
            self._scheduler_panel.setPlainText("\n".join(schedule_lines))

        if self._history_panel is not None:
            history_lines = [
                (
                    f"{execution.get('start_time', '')} | {execution.get('workflow_name', '')} | "
                    f"{execution.get('status', '')} | step={execution.get('current_step', '--')} | "
                    f"progress={self._progress_percent(execution):.0f}% | retries={execution.get('retry_count', 0)}"
                )
                for execution in workflows.get("executions", [])
                if isinstance(execution, dict)
            ]
            self._history_panel.setPlainText("\n".join(history_lines[-200:]))

    def _progress_percent(self, execution: dict[str, object]) -> float:
        completed = execution.get("completed_steps", [])
        if not isinstance(completed, list):
            return 0.0
        workflow_id = execution.get("workflow_id")
        for workflow in self._view_model.snapshot().workflows.get("workflows", []):
            if not isinstance(workflow, dict) or workflow.get("workflow_id") != workflow_id:
                continue
            steps = workflow.get("steps", [])
            if isinstance(steps, list) and steps:
                return min(100.0, (len(completed) / len(steps)) * 100.0)
        return 100.0 if execution.get("status") == "Completed" else 0.0

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

            QWidget#metricCard, QWidget#serviceRow {
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

            QLabel#serviceName {
                color: #111827;
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

            QTabWidget::pane {
                border: 0;
            }

            QTabBar::tab {
                min-width: 150px;
                min-height: 32px;
                padding: 6px 12px;
                margin-right: 6px;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                background-color: #ffffff;
                color: #334155;
            }

            QTabBar::tab:selected {
                background-color: #e8f6ed;
                border-color: #b7d7c0;
                color: #14532d;
                font-weight: 600;
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
