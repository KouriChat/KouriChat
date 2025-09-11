"""
公告管理模块

处理系统公告的获取、存储和显示。
公告内容从云端配置中获取，可以包含HTML格式的富文本内容。
"""

import logging
import json
import os
import hashlib
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger("autoupdate.announcement")

class AnnouncementManager:
    """公告管理器"""
    
    def __init__(self):
        """初始化公告管理器"""
        self.announcements = []
        self.current_announcement = None
        self.has_new_announcement = False
        self.last_check_time = None
        self.dismissed_announcements = set()  # 存储被用户忽略的公告ID
        # 计算dismissed_announcements.json文件路径（与announcement_manager.py同级的cloud目录）
        current_dir = os.path.dirname(os.path.abspath(__file__))  # announcement目录
        autoupdate_dir = os.path.dirname(current_dir)  # autoupdate目录
        cloud_dir = os.path.join(autoupdate_dir, "cloud")  # cloud目录
        self.dismissed_file_path = os.path.join(cloud_dir, "dismissed_announcements.json")
        self._load_dismissed_announcements()
    
    def process_announcements(self, cloud_info: Dict[str, Any]) -> bool:
        """
        处理从云端获取的公告信息
        
        Args:
            cloud_info: 云端配置信息
            
        Returns:
            bool: 是否有新公告
        """
        try:
            self.last_check_time = datetime.now()
            
            # 优先检查是否包含专用公告信息
            if "version_info" in cloud_info and "announcement" in cloud_info["version_info"]:
                announcement = cloud_info["version_info"]["announcement"]
                
                # 检查公告是否启用
                if announcement.get("enabled", False):
                    # 添加ID字段（如果没有的话）
                    if "id" not in announcement:
                        # 基于创建时间和标题生成ID
                        created_at = announcement.get("created_at", datetime.now().isoformat())
                        title = announcement.get("title", "announcement")
                        announcement["id"] = f"custom_{hashlib.md5((created_at + title).encode()).hexdigest()[:16]}"
                    
                    # 检查是否是新公告
                    is_new = self._is_new_announcement(announcement)
                    
                    if is_new:
                        logger.info(f"New announcement received: {announcement.get('title', 'Untitled')}")
                        self.current_announcement = announcement
                        self.announcements.append(announcement)
                        self.has_new_announcement = True
                        return True
            
            # 如果没有专用公告，从版本信息生成公告
            elif "version_info" in cloud_info:
                version_info = cloud_info["version_info"]
                
                # 基于版本信息生成公告
                generated_announcement = self._generate_announcement_from_version(version_info)
                
                if generated_announcement:
                    # 检查是否是新公告
                    is_new = self._is_new_announcement(generated_announcement)
                    
                    if is_new:
                        logger.info(f"Generated announcement from version info: {generated_announcement.get('title', 'Untitled')}")
                        self.current_announcement = generated_announcement
                        self.announcements.append(generated_announcement)
                        self.has_new_announcement = True
                        return True
            
            return False
        except Exception as e:
            logger.error(f"Error processing announcements: {str(e)}")
            return False
    
    def _generate_announcement_from_version(self, version_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        从版本信息生成公告
        
        Args:
            version_info: 版本信息
            
        Returns:
            Optional[Dict[str, Any]]: 生成的公告信息，如果无法生成则返回None
        """
        try:
            version = version_info.get("version", "未知")
            last_update = version_info.get("last_update", "未知")
            description = version_info.get("description", "")
            changelog = version_info.get("changelog", [])
            is_critical = version_info.get("is_critical", False)
            
            # 生成公告标题
            title = f"KouriChat v{version} 更新"
            if is_critical:
                title += " (重要更新)"
            
            # 生成公告内容
            content_parts = []
            
            # 添加欢迎信息
            content_parts.append(f"<h5>🎉 KouriChat v{version} 已发布！</h5>")
            
            # 添加更新日期
            content_parts.append(f"<p><strong>📅 更新日期:</strong> {last_update}</p>")
            
            # 添加描述
            if description:
                content_parts.append(f"<p><strong>📝 更新说明:</strong></p>")
                content_parts.append(f"<p>{description}</p>")
            
            # 添加更新日志
            # if changelog and isinstance(changelog, list):
            #     content_parts.append("<p><strong>🔧 更新内容:</strong></p>")
            #     content_parts.append("<ul>")
            #     for item in changelog:
            #         content_parts.append(f"<li>{item}</li>")
            #     content_parts.append("</ul>")
            
            # 添加升级建议
            if is_critical:
                content_parts.append('<div class="alert alert-warning">')
                content_parts.append('<strong>⚠️ 重要提示:</strong> 这是一个重要更新，建议立即升级以获得最佳体验和安全性。')
                content_parts.append('</div>')
            else:
                content_parts.append('<p class="text-muted">💡 <em>建议您及时更新以获得最新功能和改进。</em></p>')
            
            content = "".join(content_parts)
            
            # 生成公告ID（基于版本和日期）
            announcement_id = f"version_{version}_{last_update}".replace(".", "_").replace("-", "_")
            
            return {
                "id": announcement_id,
                "enabled": True,
                "title": title,
                "content": content,
                "created_at": f"{last_update}T00:00:00" if last_update != "未知" else datetime.now().isoformat(),
                "type": "version_update",
                "version": version,
                "is_critical": is_critical
            }
        except Exception as e:
            logger.error(f"Failed to generate announcement from version info: {str(e)}")
            return None
    
    def _is_new_announcement(self, announcement: Dict[str, Any]) -> bool:
        """
        检查是否是新公告
        
        Args:
            announcement: 公告信息
            
        Returns:
            bool: 是否是新公告
        """
        # 如果没有当前公告，则认为是新公告
        if not self.current_announcement:
            return True
        
        # 检查ID是否相同
        current_id = self.current_announcement.get("id", "")
        new_id = announcement.get("id", "")
        
        if new_id and current_id != new_id:
            return True
        
        # 检查创建时间是否更新
        try:
            current_time = datetime.fromisoformat(self.current_announcement.get("created_at", "2000-01-01T00:00:00"))
            new_time = datetime.fromisoformat(announcement.get("created_at", "2000-01-01T00:00:00"))
            
            return new_time > current_time
        except:
            # 如果时间解析失败，比较内容
            return announcement.get("content", "") != self.current_announcement.get("content", "")
    
    def get_current_announcement(self) -> Optional[Dict[str, Any]]:
        """
        获取当前公告
        
        Returns:
            Optional[Dict[str, Any]]: 当前公告信息，如果没有则返回None
        """
        return self.current_announcement
    
    def mark_as_read(self) -> None:
        """将当前公告标记为已读"""
        self.has_new_announcement = False
    
    def has_unread_announcement(self) -> bool:
        """
        检查是否有未读公告
        
        Returns:
            bool: 是否有未读公告
        """
        if not self.has_new_announcement or not self.current_announcement:
            return False
        
        # 检查当前公告是否被用户忽略
        announcement_id = self.current_announcement.get("id", "")
        if announcement_id in self.dismissed_announcements:
            return False
            
        return True
    
    def _load_dismissed_announcements(self):
        """从文件加载已忽略的公告ID"""
        try:
            if os.path.exists(self.dismissed_file_path):
                with open(self.dismissed_file_path, 'r', encoding='utf-8') as f:
                    dismissed_list = json.load(f)
                    self.dismissed_announcements = set(dismissed_list)
                    logger.debug(f"加载了 {len(self.dismissed_announcements)} 个已忽略的公告")
        except Exception as e:
            logger.warning(f"加载已忽略公告文件失败: {str(e)}")
            self.dismissed_announcements = set()
    
    def _save_dismissed_announcements(self):
        """保存已忽略的公告ID到文件"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.dismissed_file_path), exist_ok=True)
            
            with open(self.dismissed_file_path, 'w', encoding='utf-8') as f:
                json.dump(list(self.dismissed_announcements), f, ensure_ascii=False, indent=2)
                logger.debug(f"保存了 {len(self.dismissed_announcements)} 个已忽略的公告")
        except Exception as e:
            logger.error(f"保存已忽略公告文件失败: {str(e)}")

    def dismiss_announcement(self, announcement_id: str = None) -> bool:
        """
        忽略指定的公告（不再显示）
        
        Args:
            announcement_id: 公告ID，如果为None则忽略当前公告
            
        Returns:
            bool: 是否成功忽略
        """
        try:
            if announcement_id is None and self.current_announcement:
                announcement_id = self.current_announcement.get("id", "")
            
            if announcement_id:
                self.dismissed_announcements.add(announcement_id)
                self._save_dismissed_announcements()  # 持久化保存
                logger.info(f"用户忽略了公告: {announcement_id}")
                return True
            else:
                logger.warning("无法忽略公告：公告ID为空")
                return False
        except Exception as e:
            logger.error(f"忽略公告时发生错误: {str(e)}")
            return False
    
    def get_all_announcements(self) -> List[Dict[str, Any]]:
        """
        获取所有公告
        
        Returns:
            List[Dict[str, Any]]: 所有公告列表
        """
        return self.announcements

# 全局公告管理器实例
_global_announcement_manager = None

def get_announcement_manager() -> AnnouncementManager:
    """获取全局公告管理器实例"""
    global _global_announcement_manager
    if _global_announcement_manager is None:
        _global_announcement_manager = AnnouncementManager()
    return _global_announcement_manager

# 便捷函数
def process_announcements(cloud_info: Dict[str, Any]) -> bool:
    """
    处理从云端获取的公告信息
    
    Args:
        cloud_info: 云端配置信息
        
    Returns:
        bool: 是否有新公告
    """
    return get_announcement_manager().process_announcements(cloud_info)

def get_current_announcement() -> Optional[Dict[str, Any]]:
    """
    获取当前公告
    
    Returns:
        Optional[Dict[str, Any]]: 当前公告信息，如果没有则返回None
    """
    return get_announcement_manager().get_current_announcement()

def mark_announcement_as_read() -> None:
    """将当前公告标记为已读"""
    get_announcement_manager().mark_as_read()

def has_unread_announcement() -> bool:
    """
    检查是否有未读公告
    
    Returns:
        bool: 是否有未读公告
    """
    return get_announcement_manager().has_unread_announcement()

def dismiss_announcement(announcement_id: str = None) -> bool:
    """
    忽略指定的公告（不再显示）
    
    Args:
        announcement_id: 公告ID，如果为None则忽略当前公告
        
    Returns:
        bool: 是否成功忽略
    """
    return get_announcement_manager().dismiss_announcement(announcement_id)

def get_all_announcements() -> List[Dict[str, Any]]:
    """
    获取所有公告
    
    Returns:
        List[Dict[str, Any]]: 所有公告列表
    """
    return get_announcement_manager().get_all_announcements()