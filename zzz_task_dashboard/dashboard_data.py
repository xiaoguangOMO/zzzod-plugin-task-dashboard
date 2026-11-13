"""任务完成情况看板的数据采集。

数据全部来自一条龙自己的配置文件，不读写游戏、不触发任何应用运行：

- 每个实例「勾选了哪些任务」：``config/<实例>/one_dragon/_group.yml`` 的 ``app_list``；
- 每项任务今天是否完成：``config/<实例>/app_run_record/<app_id>.yml`` 的运行记录，
  按其自身的「游戏日刷新时间」判断是否跨天（跨天自动视为未运行）。

个别应用（目前是体力刷取 ``charge_plan``）每次初始化都会把运行记录重置成「未运行」，
所以对它们改看记录里的 ``dt``/``run_time`` 是否属于当前游戏日，而不是 ``run_status``。

这样看板显示的结果与一条龙「今天会不会跳过这个应用」的判定基本一致。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from one_dragon.base.config.game_account_config import GameAccountConfig
from one_dragon.base.operation.application.application_const import DEFAULT_GROUP_ID
from one_dragon.base.operation.application.application_group_config import (
    ApplicationGroupConfig,
)
from one_dragon.base.operation.application_run_record import AppRunRecord
from one_dragon.utils import os_utils
from one_dragon.utils.log_utils import log

STATUS_NOT_SELECTED = 'not_selected'  # 该实例没有勾选这项任务
STATUS_NO_RECORD = 'no_record'  # 勾选了，但没有可读的运行记录
STATUS_WAIT = 'wait'  # 今天还没运行
STATUS_SUCCESS = 'success'  # 今天已完成
STATUS_FAIL = 'fail'  # 今天运行失败
STATUS_RUNNING = 'running'  # 正在运行

STATUS_TEXT: dict[str, str] = {
    STATUS_NOT_SELECTED: '未勾选',
    STATUS_NO_RECORD: '无记录',
    STATUS_WAIT: '未运行',
    STATUS_SUCCESS: '已完成',
    STATUS_FAIL: '失败',
    STATUS_RUNNING: '运行中',
}


@dataclass
class CellStatus:
    """一个实例里某一项任务的完成情况。"""

    status: str
    run_time: str = ''  # 例如 11-12 10:03，非完成/失败时为空

    @property
    def is_done(self) -> bool:
        return self.status == STATUS_SUCCESS

    @property
    def is_selected(self) -> bool:
        return self.status != STATUS_NOT_SELECTED


@dataclass
class TaskRow:
    """看板的一行：一项任务在各实例里的完成情况。"""

    app_id: str
    app_name: str
    cells: dict[int, CellStatus] = field(default_factory=dict)


@dataclass
class InstanceInfo:
    """看板的一列：一个实例。"""

    idx: int
    name: str
    done: int = 0
    selected: int = 0


@dataclass
class DashboardData:
    """看板需要的全部数据。"""

    dt: str = ''
    collected_at: str = ''
    instances: list[InstanceInfo] = field(default_factory=list)
    rows: list[TaskRow] = field(default_factory=list)

    @property
    def total_done(self) -> int:
        return sum(instance.done for instance in self.instances)

    @property
    def total_selected(self) -> int:
        return sum(instance.selected for instance in self.instances)


# 这些应用每次初始化都会把自己的运行记录重置成「未运行」，run_status 不能用来判断今天
# 是否跑过（典型例子是体力刷取 ChargePlanRunRecord.check_and_update_status 每次都 reset）。
# 对它们改用「记录里的 dt 是不是今天、有没有运行时间」来判断。
ALWAYS_RESET_APP_IDS = frozenset({'charge_plan'})


def _ran_today(record: AppRunRecord) -> bool:
    """记录里的运行时间是否属于当前游戏日。"""
    try:
        if record.dt != record.get_current_dt():
            return False
    except Exception:
        return False
    return record.run_time not in ('', '-')


def _status_of(record: AppRunRecord | None, app_id: str = '') -> CellStatus:
    """把运行记录转换成看板单元格。"""
    if record is None:
        return CellStatus(STATUS_NO_RECORD)

    status = record.run_status_under_now
    if app_id in ALWAYS_RESET_APP_IDS:
        if record.run_status == AppRunRecord.STATUS_RUNNING:
            return CellStatus(STATUS_RUNNING)
        if _ran_today(record):
            if record.run_status == AppRunRecord.STATUS_FAIL:
                return CellStatus(STATUS_FAIL, record.run_time or '')
            return CellStatus(STATUS_SUCCESS, record.run_time or '')
        return CellStatus(STATUS_WAIT)

    if status == AppRunRecord.STATUS_SUCCESS:
        return CellStatus(STATUS_SUCCESS, record.run_time or '')
    if status == AppRunRecord.STATUS_FAIL:
        return CellStatus(STATUS_FAIL, record.run_time or '')
    if status == AppRunRecord.STATUS_RUNNING:
        return CellStatus(STATUS_RUNNING)
    return CellStatus(STATUS_WAIT)


def _safe_run_record(ctx, app_id: str, instance_idx: int) -> AppRunRecord | None:
    try:
        return ctx.run_context.get_run_record(app_id, instance_idx)
    except Exception:  # 个别应用创建记录失败不应该拖垮整个看板
        log.warning('读取应用 %s 实例 %s 的运行记录失败', app_id, instance_idx, exc_info=True)
        return None


def collect_dashboard(ctx) -> DashboardData:
    """采集所有一条龙实例的已勾选任务完成情况。"""
    instances = list(ctx.one_dragon_config.instance_list_in_od)
    data = DashboardData(collected_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    if not instances:
        data.dt = os_utils.get_dt(0)
        return data

    first_instance = instances[0]
    try:
        offset = GameAccountConfig(first_instance.idx).game_refresh_hour_offset
    except Exception:
        offset = 0
    data.dt = os_utils.get_dt(offset)

    # 直接 new 一份配置并手动补全 app_list：
    # ApplicationGroupConfig 构造时只填 _all_apps，app_list 需要 update_full_app_list
    # 才会按「已注册的默认组应用」过滤出来。这里不用 ctx.app_group_manager 的缓存，
    # 保证看板每次刷新都能看到最新勾选状态。
    default_app_ids: list[str] = list(getattr(ctx.run_context, 'default_group_apps', []) or [])
    group_configs: dict[int, ApplicationGroupConfig] = {}
    for instance in instances:
        try:
            config = ApplicationGroupConfig(instance.idx, DEFAULT_GROUP_ID)
            config.update_full_app_list(default_app_ids)
            group_configs[instance.idx] = config
        except Exception:
            log.warning('读取实例 %s 的应用组配置失败', instance.idx, exc_info=True)

    # 任务顺序：以第一个实例保存的顺序为准，其余实例新增的任务追加在后面
    ordered_app_ids: list[str] = []
    seen: set[str] = set()
    for instance in instances:
        config = group_configs.get(instance.idx)
        if config is None:
            continue
        for item in config.app_list:
            if item.app_id in seen:
                continue
            seen.add(item.app_id)
            ordered_app_ids.append(item.app_id)

    info_map: dict[int, InstanceInfo] = {}
    for instance in instances:
        info_map[instance.idx] = InstanceInfo(idx=instance.idx, name=instance.name)

    rows: list[TaskRow] = []
    for app_id in ordered_app_ids:
        if app_id == getattr(ctx, 'current_app_id', None):
            continue
        try:
            app_name = ctx.run_context.get_application_name(app_id)
        except Exception:
            # 未注册（例如插件被卸载后残留的配置项）直接跳过
            continue

        row = TaskRow(app_id=app_id, app_name=app_name)
        for instance in instances:
            config = group_configs.get(instance.idx)
            enabled = False
            if config is not None:
                for item in config.app_list:
                    if item.app_id == app_id:
                        enabled = item.enabled
                        break

            if not enabled:
                row.cells[instance.idx] = CellStatus(STATUS_NOT_SELECTED)
                continue

            cell = _status_of(_safe_run_record(ctx, app_id, instance.idx), app_id)
            row.cells[instance.idx] = cell
            info = info_map[instance.idx]
            info.selected += 1
            if cell.is_done:
                info.done += 1
        rows.append(row)

    data.instances = [info_map[instance.idx] for instance in instances]
    data.rows = rows
    return data
