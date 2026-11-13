"""让本地安装（还没上架商店）的插件在「插件管理 → 详情」里也显示使用说明。

一条龙的插件详情弹窗只从商店条目里取 ``readmeHtml``：本地插件没有商店条目，
「插件说明」区域就只剩一句「该插件暂无可展示的说明」。这里在弹窗构造前，把插件
目录里的 USAGE.md（其次 README.md）渲染成 HTML 补进去。

商店条目自带说明时保持原样，不覆盖商店内容，也不修改一条龙的源码文件。
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from one_dragon.utils.log_utils import log

from .const import APP_NAME
from .local_readme import read_readme_html

_PACKAGE_DIR = Path(__file__).resolve().parent


def apply_ui_patch() -> bool:
    """给插件详情弹窗装一个「本地说明兜底」，返回是否安装成功。

    没有 Qt 环境（例如只跑后端）时静默跳过，不影响插件本身。
    """
    try:
        from one_dragon_qt.view.plugin.plugin_detail_dialog import PluginDetailDialog
    except Exception:  # noqa: BLE001 - 没装 Qt 属于正常情况
        log.debug('任务完成看板：未加载插件详情弹窗，跳过本地说明注入')
        return False

    if getattr(PluginDetailDialog, '_task_dashboard_readme_patched', False):
        return True

    original_init = PluginDetailDialog.__init__

    def patched_init(self, data, parent=None):
        try:
            if not getattr(data, 'readme_html', '') \
                    and getattr(data, 'title', '') == APP_NAME:
                html = read_readme_html(_PACKAGE_DIR)
                if html:
                    data = dataclasses.replace(data, readme_html=html)
        except Exception:  # noqa: BLE001 - 说明只是展示，失败不能影响弹窗
            log.error('任务完成看板：读取本地说明失败', exc_info=True)
        original_init(self, data, parent)

    PluginDetailDialog.__init__ = patched_init
    PluginDetailDialog._task_dashboard_readme_patched = True
    return True
