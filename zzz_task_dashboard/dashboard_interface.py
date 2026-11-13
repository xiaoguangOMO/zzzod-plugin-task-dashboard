"""把任务完成看板做成一条龙侧栏里的一个页面。"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget
from qfluentwidgets import FluentIcon

from one_dragon.utils.log_utils import log
from one_dragon_qt.widgets.vertical_scroll_interface import VerticalScrollInterface

from .dashboard_ui import DashboardPanel

NAV_TEXT = '任务看板'
OBJECT_NAME = 'zzz_task_dashboard_interface'


class TaskDashboardInterface(VerticalScrollInterface):
    """侧栏页面：显示看板内容，切到这个页面时自动刷新。"""

    def __init__(self, ctx, parent=None):
        VerticalScrollInterface.__init__(
            self,
            content_widget=None,
            object_name=OBJECT_NAME,
            nav_text_cn=NAV_TEXT,
            nav_icon=FluentIcon.TILES,
            parent=parent,
        )
        self.ctx = ctx
        self._panel: DashboardPanel | None = None

    def get_content_widget(self) -> QWidget:
        self._panel = DashboardPanel(self.ctx)
        return self._panel

    def on_interface_shown(self) -> None:
        super().on_interface_shown()
        log.info('任务完成看板：切换到看板页面')
        if self._panel is not None:
            self._panel.set_ctx(self.ctx)

    def update_ctx(self, ctx) -> None:
        """一条龙切换实例后，重新绑定上下文。"""
        self.ctx = ctx
        if self._panel is not None:
            self._panel.set_ctx(ctx)
