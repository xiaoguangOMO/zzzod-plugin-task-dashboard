"""独立启动「任务完成看板」，不经过一条龙的界面。

用法（二选一）：

1. 双击桌面快捷方式「任务完成看板」；
2. 命令行：

   ```
   <一条龙目录>\\.venv\\Scripts\\pythonw.exe <一条龙目录>\\plugins\\zzz_task_dashboard\\standalone.py
   ```

它会自己推导一条龙目录、把 ``src`` 加进 sys.path，然后单独开一个窗口显示看板。
不会启动游戏，也不会启动一条龙主界面，可以连续多次打开。
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path


def _prepare_paths() -> Path:
    """把一条龙的 src 与 plugins 加进 sys.path，返回一条龙根目录。"""
    repo_root = Path(__file__).resolve().parents[2]
    src_dir = repo_root / 'src'
    plugin_dir = repo_root / 'plugins'
    for path in (str(src_dir), str(plugin_dir)):
        if path not in sys.path:
            sys.path.insert(0, path)
    return repo_root


def main() -> int:
    repo_root = _prepare_paths()

    from PySide6.QtWidgets import QApplication
    from qfluentwidgets import Theme, setTheme

    app = QApplication(sys.argv)
    setTheme(Theme.AUTO)

    # 先显示一个提示窗，避免初始化那十几秒里什么都不出现
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

    splash = QWidget()
    splash.setWindowTitle('任务完成看板')
    splash.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    splash.resize(360, 120)
    splash_layout = QVBoxLayout(splash)
    splash_label = QLabel('正在读取一条龙配置，请稍候…', splash)
    splash_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    splash_layout.addWidget(splash_label)
    splash.show()
    app.processEvents()

    started = time.time()
    try:
        from zzz_od.context.zzz_context import ZContext

        ctx = ZContext()
        ctx.init()
    except Exception as exc:  # 初始化失败时给出可读提示，而不是直接闪退
        splash_label.setText(f'读取配置失败：{exc}')
        app.processEvents()
        return app.exec()

    elapsed = time.time() - started
    print(f'初始化完成，用时 {elapsed:.1f} 秒', file=sys.stderr)

    splash.close()

    from zzz_task_dashboard.dashboard_ui import TaskDashboardDialog

    window = TaskDashboardDialog(ctx)
    window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
    window.show()
    window.raise_()
    window.activateWindow()

    if os.environ.get('ZZZ_DASHBOARD_SELFTEST'):
        # 离线自检用：显示一下窗口就退出
        from PySide6.QtCore import QTimer

        QTimer.singleShot(1500, app.quit)

    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
