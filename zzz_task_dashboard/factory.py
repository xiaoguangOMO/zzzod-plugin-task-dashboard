from one_dragon.base.operation.application.application_factory import ApplicationFactory
from zzz_od.context.zzz_context import ZContext

from . import const
from .app import TaskDashboardApp


class TaskDashboardFactory(ApplicationFactory):

    def __init__(self, ctx: ZContext):
        ApplicationFactory.__init__(self, const)
        self.ctx: ZContext = ctx

    def create_application(self, instance_idx: int, group_id: str) -> TaskDashboardApp:
        return TaskDashboardApp(self.ctx, instance_idx, group_id)
