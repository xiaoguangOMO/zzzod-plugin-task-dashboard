"""任务完成看板的应用入口。

在一条龙的「应用运行」里运行这个应用，会打开一个窗口，列出所有一条龙实例里
**已勾选**的任务以及它们今天是否完成。它不启动游戏、不执行任何日常任务，
只是读取各实例的 ``_group.yml`` 与 ``app_run_record``。
"""

from __future__ import annotations

from one_dragon.base.operation.application_base import Application
from one_dragon.base.operation.operation_node import operation_node
from one_dragon.base.operation.operation_round_result import OperationRoundResult
from one_dragon.utils.log_utils import log
from zzz_od.context.zzz_context import ZContext

from . import const
from .dashboard_ui import request_show


class TaskDashboardApp(Application):

    def __init__(self, ctx: ZContext, instance_idx: int, group_id: str):
        Application.__init__(
            self,
            ctx,
            app_id=const.APP_ID,
            node_max_retry_times=1,
            op_name=const.APP_NAME,
            need_check_game_win=False,
            use_factory_run_record=False,
        )

    @operation_node(name='打开任务完成看板', is_start_node=True, screenshot_before_round=False)
    def open_dashboard(self) -> OperationRoundResult:
        if request_show(self.ctx):
            return self.round_success('已打开任务完成看板')
        log.error('任务完成看板：界面桥接不可用，无法打开窗口')
        return self.round_fail('当前不是图形界面环境，无法打开看板窗口')
