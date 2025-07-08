from threading import Thread
from typing import List, Tuple, Optional
import json

from app.core.cache import cached, cache_backend
from app.core.config import settings
from app.db.models.workflow import Workflow as WorkflowModel
from app.db.systemconfig_oper import SystemConfigOper
from app.log import logger
from app.schemas.types import SystemConfigKey
from app.utils.http import RequestUtils
from app.utils.singleton import WeakSingleton
from app.utils.system import SystemUtils


class WorkflowHelper(metaclass=WeakSingleton):
    """
    工作流分享等
    """

    _workflow_share = f"{settings.MP_SERVER_HOST}/workflow/share"

    _workflow_shares = f"{settings.MP_SERVER_HOST}/workflow/shares"

    _workflow_fork = f"{settings.MP_SERVER_HOST}/workflow/fork/%s"

    _shares_cache_region = "workflow_share"

    _share_user_id = None

    def __init__(self):
        self.get_user_uuid()

    def workflow_share(self, workflow_id: int,
                       share_title: str, share_comment: str, share_user: str) -> Tuple[bool, str]:
        """
        分享工作流
        """
        if not settings.SUBSCRIBE_STATISTIC_SHARE:  # 复用订阅分享的配置
            return False, "当前没有开启数据共享功能"
        
        # 获取工作流信息
        from app.db import get_db
        db = next(get_db())
        workflow = WorkflowModel.get(db, workflow_id)
        if not workflow:
            return False, "工作流不存在"
        
        workflow_dict = workflow.to_dict()
        workflow_dict.pop("id")
        
        # 清除缓存
        cache_backend.clear(region=self._shares_cache_region)
        
        # 发送分享请求
        res = RequestUtils(proxies=settings.PROXY or {}, content_type="application/json",
                           timeout=10).post(self._workflow_share,
                                            json={
                                                "share_title": share_title,
                                                "share_comment": share_comment,
                                                "share_user": share_user,
                                                "share_uid": self._share_user_id,
                                                **workflow_dict
                                            })
        if res is None:
            return False, "连接MoviePilot服务器失败"
        if res.ok:
            # 清除 get_shares 的缓存，以便实时看到结果
            cache_backend.clear(region=self._shares_cache_region)
            return True, ""
        else:
            return False, res.json().get("message")

    def share_delete(self, share_id: int) -> Tuple[bool, str]:
        """
        删除分享
        """
        if not settings.SUBSCRIBE_STATISTIC_SHARE:  # 复用订阅分享的配置
            return False, "当前没有开启数据共享功能"
        
        res = RequestUtils(proxies=settings.PROXY or {},
                           timeout=5).delete_res(f"{self._workflow_share}/{share_id}",
                                                 params={"share_uid": self._share_user_id})
        if res is None:
            return False, "连接MoviePilot服务器失败"
        if res.ok:
            # 清除 get_shares 的缓存，以便实时看到结果
            cache_backend.clear(region=self._shares_cache_region)
            return True, ""
        else:
            return False, res.json().get("message")

    def workflow_fork(self, share_id: int) -> Tuple[bool, str]:
        """
        复用分享的工作流
        """
        if not settings.SUBSCRIBE_STATISTIC_SHARE:  # 复用订阅分享的配置
            return False, "当前没有开启数据共享功能"
        
        res = RequestUtils(proxies=settings.PROXY or {}, timeout=5, headers={
            "Content-Type": "application/json"
        }).get_res(self._workflow_fork % share_id)
        if res is None:
            return False, "连接MoviePilot服务器失败"
        if res.ok:
            return True, ""
        else:
            return False, res.json().get("message")

    @cached(region=_shares_cache_region)
    def get_shares(self, name: Optional[str] = None, page: Optional[int] = 1, count: Optional[int] = 30) -> List[dict]:
        """
        获取工作流分享数据
        """
        if not settings.SUBSCRIBE_STATISTIC_SHARE:  # 复用订阅分享的配置
            return []
        
        res = RequestUtils(proxies=settings.PROXY or {}, timeout=15).get_res(self._workflow_shares, params={
            "name": name,
            "page": page,
            "count": count
        })
        if res and res.status_code == 200:
            return res.json()
        return []

    def get_user_uuid(self) -> str:
        """
        获取用户uuid
        """
        if not self._share_user_id:
            self._share_user_id = SystemUtils.generate_user_unique_id()
            logger.info(f"当前用户UUID: {self._share_user_id}")
        return self._share_user_id or ""