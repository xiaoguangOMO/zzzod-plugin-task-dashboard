"""任务完成看板的界面。

界面由两部分组成：

* ``DashboardPanel``：只放内容（汇总、表格、图例、过滤、刷新），既能塞进对话框，
  也能塞进一条龙的侧栏页面；
* ``TaskDashboardDialog``：独立对话框，用于「应用运行」入口和独立启动脚本。

一条龙的应用运行在工作线程里，而 Qt 控件必须只在主线程创建。这里的做法是：
插件被导入时先建一个 ``_DashboardBridge``，把它的线程亲和性挪到 GUI 主线程，
应用运行时从工作线程发信号，槽函数由 Qt 排队回主线程执行，再在那里打开窗口。
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CheckBox,
    PushButton,
    TableWidget,
    isDarkTheme,
)

from one_dragon.utils.log_utils import log

from .dashboard_data import (
    STATUS_FAIL,
    STATUS_NOT_SELECTED,
    STATUS_RUNNING,
    STATUS_SUCCESS,
    STATUS_TEXT,
    STATUS_WAIT,
    CellStatus,
    DashboardData,
    collect_dashboard,
)
from .task_details import collect_detail_lines, has_details

WINDOW_TITLE = '任务完成看板'
WINDOW_WIDTH = 860
WINDOW_HEIGHT = 700
TASK_COLUMN_WIDTH = 320
INSTANCE_COLUMN_WIDTH = 146
ROW_HEIGHT = 36
AUTO_REFRESH_MS = 30_000


def _status_color(status: str) -> QColor:
    dark = isDarkTheme()
    if status == STATUS_SUCCESS:
        return QColor('#3fb950' if dark else '#1a7f37')
    if status == STATUS_FAIL:
        return QColor('#f85149' if dark else '#cf222e')
    if status == STATUS_RUNNING:
        return QColor('#d29922' if dark else '#9a6700')
    if status == STATUS_WAIT:
        return QColor('#ffa657' if dark else '#bc4c00')
    return QColor('#8b949e' if dark else '#6e7781')


def _cell_text(cell: CellStatus) -> str:
    if cell.run_time and cell.status in (STATUS_SUCCESS, STATUS_FAIL):
        # run_time 形如 11-13 18:27：带月日，才知道是不是今天这一刻跑的
        mark = '✓' if cell.status == STATUS_SUCCESS else '✗'
        return f'{mark} {cell.run_time}'
    return STATUS_TEXT.get(cell.status, '')


class DashboardPanel(QWidget):
    """看板内容：汇总 + 表格 + 图例 + 过滤。"""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._data: DashboardData | None = None
        self._timer: QTimer | None = None
        self._expanded_app_ids: set[str] = set()
        self._app_id_by_row: dict[int, str] = {}

        self._build_ui()
        self.refresh()

        self._timer = QTimer(self)
        self._timer.setInterval(AUTO_REFRESH_MS)
        self._timer.timeout.connect(self._on_timer)
        self._timer.start()

    # ---------- 界面 ----------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.summary_label = BodyLabel('正在采集…', self)
        layout.addWidget(self.summary_label)

        self.instance_label = CaptionLabel('', self)
        layout.addWidget(self.instance_label)

        self.table = TableWidget(self)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.setBorderVisible(True)
        self.table.setBorderRadius(8)
        self.table.setMinimumHeight(320)
        self.table.cellClicked.connect(self._on_cell_clicked)
        layout.addWidget(self.table, 1)

        self.legend_label = CaptionLabel(
            '✓ 已完成（后面是日期与时刻）　✗ 失败　未运行 = 今天还没跑　'
            '未勾选 = 该实例没勾这项　▸ 带这个标记的任务可以点开看详情',
            self,
        )
        layout.addWidget(self.legend_label)

        self.hint_label = CaptionLabel(
            f'每 {AUTO_REFRESH_MS // 1000} 秒自动刷新；数据来自各实例的 app_run_record，跨天自动视为未运行。',
            self,
        )
        layout.addWidget(self.hint_label)

        button_row = QHBoxLayout()
        self.only_selected_check = CheckBox('只看已勾选任务', self)
        self.only_selected_check.setChecked(True)
        self.only_selected_check.stateChanged.connect(self._on_filter_changed)
        button_row.addWidget(self.only_selected_check)
        button_row.addStretch(1)
        self.refresh_button = PushButton('刷新', self)
        self.refresh_button.clicked.connect(self.refresh)
        button_row.addWidget(self.refresh_button)
        layout.addLayout(button_row)

    # ---------- 数据 ----------

    def set_ctx(self, ctx) -> None:
        self.ctx = ctx
        self.refresh()

    def refresh(self) -> None:
        try:
            data = collect_dashboard(self.ctx)
        except Exception:
            log.error('采集任务完成情况失败', exc_info=True)
            self.summary_label.setText('采集失败，请查看日志')
            return

        self._data = data
        self._render(data)

    def _on_timer(self) -> None:
        # 页面/窗口不可见时不采集，省得在后台空转
        if self.isVisible():
            self.refresh()

    def _on_filter_changed(self) -> None:
        if self._data is not None:
            self._render(self._data)

    def _on_cell_clicked(self, row_index: int, column: int) -> None:
        """点任务名（或它左边那一列）展开/收起详情。"""
        if column != 0:
            return
        app_id = self._app_id_by_row.get(row_index)
        if app_id is None or not has_details(app_id):
            return
        if app_id in self._expanded_app_ids:
            self._expanded_app_ids.discard(app_id)
        else:
            self._expanded_app_ids.add(app_id)
        if self._data is not None:
            self._render(self._data)

    def _render(self, data: DashboardData) -> None:
        self.summary_label.setText(
            f'游戏日 {data.dt} · 共完成 {data.total_done} / {data.total_selected} 项'
        )
        self.instance_label.setText(
            '　'.join(
                f'实例 {instance.name}：{instance.done}/{instance.selected}'
                for instance in data.instances
            )
            or '没有需要在一条龙里运行的实例'
        )

        self.table.clear()
        self.table.clearSpans()
        self._app_id_by_row = {}
        headers = ['任务'] + [
            f'实例 {instance.name}' for instance in data.instances
        ]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        rows = data.rows
        if self.only_selected_check.isChecked():
            rows = [
                row for row in rows
                if any(cell.is_selected for cell in row.cells.values())
            ]

        expanded_rows = [row for row in rows if row.app_id in self._expanded_app_ids]
        self.table.setRowCount(len(rows) + len(expanded_rows))

        row_index = 0
        for row in rows:
            expandable = has_details(row.app_id)
            marker = ''
            if expandable:
                marker = '▾ ' if row.app_id in self._expanded_app_ids else '▸ '

            name_item = QTableWidgetItem(f'{marker}{row.app_name}')
            name_item.setToolTip(
                f'{row.app_id}（点击{"收起" if row.app_id in self._expanded_app_ids else "展开"}详情）'
                if expandable else row.app_id
            )
            self.table.setItem(row_index, 0, name_item)
            self._app_id_by_row[row_index] = row.app_id
            # 显式设置普通行行高：QTableWidget 的行高按行号保留，
            # 详情行被删除后原来的高行高会留给下一行（例如「丽都城募」被撑大）
            self.table.setRowHeight(row_index, ROW_HEIGHT)

            for column_offset, instance in enumerate(data.instances, start=1):
                cell = row.cells.get(instance.idx, CellStatus(STATUS_NOT_SELECTED))
                item = QTableWidgetItem(_cell_text(cell))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setForeground(_status_color(cell.status))
                item.setToolTip(
                    f'最近运行：{cell.run_time}' if cell.run_time
                    else STATUS_TEXT.get(cell.status, '')
                )
                self.table.setItem(row_index, column_offset, item)

            row_index += 1

            if expandable and row.app_id in self._expanded_app_ids:
                self._add_detail_row(row_index, row.app_id, data, len(headers))
                row_index += 1

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, len(headers)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(column, INSTANCE_COLUMN_WIDTH)

        # 实例多的时候把对话框撑宽，避免后面的实例列被挤到可视区外；
        # 在一条龙主窗口的侧栏页面里则不动窗口大小。
        needed_width = TASK_COLUMN_WIDTH + INSTANCE_COLUMN_WIDTH * len(data.instances) + 80
        window = self.window()
        if (window is not None and window is not self
                and isinstance(window, QDialog) and window.width() < needed_width):
            window.resize(needed_width, window.height())

    def _add_detail_row(self, row_index: int, app_id: str, data: DashboardData,
                        column_count: int) -> None:
        """在任务行下面插一行跨列的详情。"""
        container = QWidget(self.table)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 6, 12, 8)
        layout.setSpacing(4)

        line_total = 0
        for instance in data.instances:
            lines = collect_detail_lines(self.ctx, app_id, instance.idx)
            if not lines:
                lines = ['没有可展开的配置信息']
            text = '<br/>'.join(lines)
            label = QLabel(
                f'<b>实例 {instance.name}</b><br/>{text}',
                container,
            )
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setWordWrap(True)
            label.setStyleSheet(
                'color: #8b949e;' if isDarkTheme() else 'color: #57606a;'
            )
            layout.addWidget(label)
            line_total += len(lines) + 1

        self.table.setSpan(row_index, 0, 1, column_count)
        self.table.setCellWidget(row_index, 0, container)
        self.table.setRowHeight(row_index, max(56, 22 * line_total + 12))


class TaskDashboardDialog(QDialog):
    """独立对话框：应用运行入口和独立启动脚本用。"""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._timer: QTimer | None = None

        self.setWindowTitle(WINDOW_TITLE)
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(10)

        self.panel = DashboardPanel(ctx, self)
        layout.addWidget(self.panel, 1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.close_button = PushButton('关闭', self)
        self.close_button.clicked.connect(self.close)
        button_row.addWidget(self.close_button)
        layout.addLayout(button_row)

    def refresh(self) -> None:
        self.panel.refresh()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt 约定
        _forget_window(self)
        super().closeEvent(event)


_window: TaskDashboardDialog | None = None


def _forget_window(dialog: TaskDashboardDialog) -> None:
    global _window
    if _window is dialog:
        _window = None


def open_dashboard(ctx, parent=None) -> TaskDashboardDialog:
    """打开（或刷新已打开的）看板窗口。必须在主线程调用。"""
    global _window
    if _window is not None:
        try:
            _window.ctx = ctx
            _window.panel.set_ctx(ctx)
            _window.show()
            _window.raise_()
            _window.activateWindow()
            return _window
        except RuntimeError:
            _window = None

    if parent is None:
        parent = QApplication.activeWindow()

    _window = TaskDashboardDialog(ctx, parent)
    _window.show()
    _window.raise_()
    _window.activateWindow()
    return _window


class _DashboardBridge(QObject):
    """把工作线程的「打开看板」请求排队回主线程。"""

    request_show = Signal()

    def __init__(self):
        super().__init__()
        self.ctx = None
        self.request_show.connect(self._on_request, Qt.ConnectionType.QueuedConnection)

    @Slot()
    def _on_request(self) -> None:
        try:
            open_dashboard(self.ctx)
        except Exception:
            log.error('打开任务完成看板失败', exc_info=True)


_bridge: _DashboardBridge | None = None


class MainThreadRunner(QObject):
    """把任意可调用对象排队到 GUI 主线程执行。

    插件是在 ``CtxInitRunner`` 这个后台线程里被导入的，创建控件前必须先回到主线程。
    """

    def __init__(self, func):
        super().__init__()
        self._func = func

    @Slot()
    def run(self) -> None:
        try:
            self._func()
        except Exception:
            log.error('任务完成看板主线程任务执行失败', exc_info=True)


def run_in_main_thread(func) -> bool:
    """把 func 排队到 GUI 主线程。可以从任意线程调用。"""
    app = QApplication.instance()
    if app is None:
        return False

    runner = MainThreadRunner(func)
    if runner.thread() is not app.thread():
        runner.moveToThread(app.thread())

    if not hasattr(run_in_main_thread, '_runners'):
        run_in_main_thread._runners = []
    run_in_main_thread._runners.append(runner)  # 防止被回收

    from PySide6.QtCore import QMetaObject

    QMetaObject.invokeMethod(runner, 'run', Qt.ConnectionType.QueuedConnection)
    return True


def ensure_bridge() -> _DashboardBridge | None:
    """创建桥接对象，并确保它归属 GUI 主线程。

    插件是在一条龙初始化上下文时被导入的，而那次初始化跑在一个 QThread 里
    （``CtxInitRunner``），所以这里的创建线程往往不是 GUI 线程。若桥接对象留在
    那个线程，它的 queued 槽永远不会被调用（线程结束后没有事件循环），窗口也就
    永远不出现。moveToThread 必须在对象所属线程里调用，正好就是这里。
    """
    global _bridge
    if _bridge is not None:
        return _bridge

    app = QApplication.instance()
    if app is None:
        return None

    try:
        bridge = _DashboardBridge()
        if bridge.thread() is not app.thread():
            bridge.moveToThread(app.thread())
        _bridge = bridge
    except Exception:
        log.warning('任务完成看板界面桥接创建失败', exc_info=True)
        return None

    return _bridge


def request_show(ctx) -> bool:
    """请求打开看板。可以从任意线程调用。"""
    bridge = ensure_bridge()
    if bridge is None:
        return False

    bridge.ctx = ctx
    bridge.request_show.emit()
    log.info('任务完成看板：已请求打开窗口（%s）', datetime.now().strftime('%H:%M:%S'))
    return True
