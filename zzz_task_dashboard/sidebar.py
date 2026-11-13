"""把看板页面挂到一条龙主窗口的侧栏上。

难点是线程：插件是在一条龙初始化上下文的后台线程里被导入的，而创建控件、改导航栏
必须在 GUI 主线程。这里用 ``run_in_main_thread`` 把安装动作排队回主线程，主窗口此时
已经创建完毕（它比上下文初始化更早），所以一般一次就能装上。

如果那一次没找到主窗口（例如独立启动脚本里没有主窗口），就按 ``RETRY_DELAY_MS``
重试几次，超过次数就放弃，不影响插件其它功能。
"""

from __future__ import annotations

import os

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from one_dragon.utils.log_utils import log

from .dashboard_interface import OBJECT_NAME, TaskDashboardInterface
from .dashboard_ui import run_in_main_thread

RETRY_DELAY_MS = 800
MAX_ATTEMPTS = 15


def _find_main_window(app: QApplication):
    try:
        from one_dragon_qt.windows.main_app_window_base import MainAppWindowBase
    except Exception:
        return None

    for widget in app.topLevelWidgets():
        if isinstance(widget, MainAppWindowBase):
            return widget
    return None


def install_sidebar(ctx=None, window=None) -> bool:
    """在主窗口侧栏添加「任务看板」页面。必须在主线程调用。"""
    app = QApplication.instance()
    if app is None:
        return False

    if window is None:
        window = _find_main_window(app)
    if window is None:
        return False

    if ctx is None:
        ctx = getattr(window, 'ctx', None)
    if ctx is None:
        return False

    try:
        if window.findChild(TaskDashboardInterface, OBJECT_NAME) is not None:
            return True

        interface = TaskDashboardInterface(ctx)
        window.add_sub_interface(interface)
        log.info('任务完成看板：已添加到侧栏「%s」', interface.nav_text)
        return True
    except Exception:
        log.error('任务完成看板：添加到侧栏失败', exc_info=True)
        return False


def _schedule(attempt: int = 1) -> None:
    ok = install_sidebar()
    if ok or attempt >= MAX_ATTEMPTS:
        if not ok:
            log.info('任务完成看板：未找到一条龙主窗口，跳过侧栏按钮')
        return

    QTimer.singleShot(RETRY_DELAY_MS, lambda: _schedule(attempt + 1))


def install_sidebar_async(ctx=None) -> bool:
    """从任意线程请求把看板页面挂到侧栏。"""
    return run_in_main_thread(lambda: _schedule())
