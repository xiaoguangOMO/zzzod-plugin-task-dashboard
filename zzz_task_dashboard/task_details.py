"""部分任务的「详情」：从一条龙自己的应用配置里读出计划细节。

看板主表只回答「今天做完没有」，但像体力刷取（``charge_plan``）这种任务，
用户还想知道「今天排了什么、跑了几次」。这里按应用 ID 提供可读的详情行，
数据同样只来自 ``config/<实例号>/one_dragon/<应用ID>.yml``，只读不写。

没有详情的任务返回空列表，界面上也不会出现展开标记。
"""

from __future__ import annotations

from pathlib import Path

import yaml

from one_dragon.utils import os_utils
from one_dragon.utils.log_utils import log

# 有详情可展开的应用
DETAIL_APP_IDS = ('charge_plan', 'lost_void')


def has_details(app_id: str) -> bool:
    """这个任务是否有可展开的详情。"""
    return app_id in DETAIL_APP_IDS


def _config_path(instance_idx: int, app_id: str) -> Path:
    work_dir = os_utils.get_work_dir()
    return Path(work_dir) / 'config' / f'{instance_idx:02d}' / 'one_dragon' / f'{app_id}.yml'


def _load_config(instance_idx: int, app_id: str) -> dict:
    path = _config_path(instance_idx, app_id)
    if not path.is_file():
        return {}
    try:
        with path.open('r', encoding='utf-8') as file:
            data = yaml.safe_load(file)
        return data if isinstance(data, dict) else {}
    except (OSError, yaml.YAMLError):
        log.warning('读取任务详情配置失败：%s', app_id, exc_info=True)
        return {}


def _switch_text(value) -> str:
    return '开' if value else '关'


def _charge_plan_lines(config: dict) -> list[str]:
    lines: list[str] = []
    plans = config.get('plan_list') or []
    if isinstance(plans, list):
        for index, plan in enumerate(plans, start=1):
            if not isinstance(plan, dict):
                continue
            category = plan.get('category_name') or ''
            mission = plan.get('mission_name') or ''
            mission_type = plan.get('mission_type_name') or ''
            run_times = plan.get('run_times', 0)
            plan_times = plan.get('plan_times', 0)
            title = ' · '.join(part for part in (category, mission) if part)
            if mission_type:
                title = f'{title}（{mission_type}）' if title else mission_type
            lines.append(f'{index}. {title}　已运行 {run_times}/{plan_times} 次')
    if not lines:
        lines.append('还没有配置体力计划')

    restore = config.get('restore_charge') or ''
    if restore:
        lines.append(f'电量不足时：{restore}')
    lines.append(
        f'双倍活动：{_switch_text(config.get("double_reward"))}'
        f'　循环执行：{_switch_text(config.get("loop"))}'
        f'　跳过计划：{_switch_text(config.get("skip_plan"))}'
        f'　每日重置计划次数：{_switch_text(config.get("daily_reset_plan_times"))}'
    )
    return lines


def _lost_void_lines(config: dict) -> list[str]:
    lines: list[str] = []
    mission = config.get('mission_name') or ''
    if mission:
        lines.append(f'任务：{mission}')
    challenge = config.get('challenge_config') or ''
    if challenge:
        lines.append(f'挑战配置：{challenge}')
    plan_times = config.get('daily_plan_times')
    if plan_times is not None:
        lines.append(f'每天计划次数：{plan_times}')
    return lines or ['还没有配置迷失之地计划']


def collect_detail_lines(ctx, app_id: str, instance_idx: int) -> list[str]:
    """返回某个实例上某任务的可读详情行；没有详情时返回空列表。"""
    if not has_details(app_id):
        return []

    config = _load_config(instance_idx, app_id)
    if app_id == 'charge_plan':
        return _charge_plan_lines(config)
    if app_id == 'lost_void':
        return _lost_void_lines(config)
    return []
