"""任务完成看板插件的入口。

插件被一条龙导入时（发生在初始化上下文的后台线程里）做三件事：

1. 给「插件管理 → 详情」弹窗补上本地说明（没上架商店时也能看到用法）；
2. 建立「打开窗口」的跨线程桥接，供「应用运行」入口使用；
3. 延后一点把看板页面挂到主窗口侧栏，提供一个随时可点的按钮。
"""

from __future__ import annotations

from one_dragon.utils.log_utils import log

try:
    from .ui_patch import apply_ui_patch

    apply_ui_patch()
except Exception:
    log.debug('任务完成看板：插件详情说明注入跳过', exc_info=True)

try:
    from .dashboard_ui import ensure_bridge, run_in_main_thread
    from .sidebar import install_sidebar_async

    ensure_bridge()

    def _install_sidebar() -> None:
        """延后安装侧栏按钮：等主窗口和上下文都就绪。"""
        from PySide6.QtCore import QTimer

        QTimer.singleShot(1500, lambda: install_sidebar_async(None))

    run_in_main_thread(_install_sidebar)
except Exception:
    log.error('任务完成看板：界面初始化失败', exc_info=True)
