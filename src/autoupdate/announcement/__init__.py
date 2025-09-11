"""
公告模块

提供系统公告的管理和显示功能。
"""

from .announcement_manager import (
    get_current_announcement,
    mark_announcement_as_read,
    has_unread_announcement,
    get_all_announcements,
    process_announcements,
    dismiss_announcement
)

# 导入UI组件（可选，如果不需要UI可以不导入）
try:
    from .announcement_ui import (
        show_announcement_dialog,
        show_if_has_announcement,
        AnnouncementWindow
    )
    has_ui = True
except ImportError:
    # 如果没有tkinter或其他UI依赖，UI组件将不可用
    has_ui = False

__all__ = [
    'get_current_announcement',
    'mark_announcement_as_read',
    'has_unread_announcement',
    'get_all_announcements',
    'process_announcements',
    'dismiss_announcement'
]

# 如果UI组件可用，添加到导出列表
if has_ui:
    __all__.extend([
        'show_announcement_dialog',
        'show_if_has_announcement',
        'AnnouncementWindow'
    ])