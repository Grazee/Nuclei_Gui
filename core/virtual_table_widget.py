"""
虚拟滚动表格组件 - 用于优化大量数据的显示性能
"""
from PyQt5.QtWidgets import (
    QTableWidget, QTableWidgetItem, QHeaderView, QApplication
)
from PyQt5.QtCore import Qt, QRect, pyqtSignal
from PyQt5.QtGui import QColor, QFont

import math


class VirtualTableWidget(QTableWidget):
    """虚拟滚动表格 - 只渲染可见区域的行"""
    
    visible_range_changed = pyqtSignal(int, int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._total_row_count = 0
        self._visible_rows = {}  # 缓存可见行的item
        self._row_height = 24  # 默认行高
        self._pending_update = False
        
        # 启用虚拟滚动
        self.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
        self.verticalScrollBar().valueChanged.connect(self._update_visible_rows)
        
    def set_total_row_count(self, count):
        """设置总行数（虚拟）"""
        self._total_row_count = count
        # 设置一个足够大的行数来支持滚动
        super().setRowCount(max(count, 10000))
        # 强制更新可见区域
        self._update_visible_rows()
        
    def get_total_row_count(self):
        """获取总行数"""
        return self._total_row_count
        
    def _get_visible_range(self):
        """计算当前可见的行范围"""
        viewport_rect = self.viewport().rect()
        top_row = self.indexAt(viewport_rect.topLeft()).row()
        bottom_row = self.indexAt(viewport_rect.bottomRight()).row()
        
        # 扩展范围以处理滚动时的过渡
        top_row = max(0, top_row - 5)
        bottom_row = min(self._total_row_count - 1, bottom_row + 5)
        
        return top_row, bottom_row
        
    def _update_visible_rows(self):
        """更新可见区域的行"""
        if self._total_row_count == 0:
            return
            
        top_row, bottom_row = self._get_visible_range()
        
        # 清理不再可见的行
        rows_to_remove = []
        for row in self._visible_rows.keys():
            if row < top_row or row > bottom_row:
                rows_to_remove.append(row)
        
        for row in rows_to_remove:
            for col in range(self.columnCount()):
                self.setItem(row, col, None)
            del self._visible_rows[row]
        
        # 触发可见范围变化信号
        self.visible_range_changed.emit(top_row, bottom_row)
        
    def set_item_for_row(self, row, items):
        """为指定行设置所有列的item"""
        if row < 0 or row >= self._total_row_count:
            return
            
        for col, item in enumerate(items):
            self.setItem(row, col, item)
        
        self._visible_rows[row] = items
        
    def clear_visible_cache(self):
        """清除可见行缓存"""
        for row in list(self._visible_rows.keys()):
            for col in range(self.columnCount()):
                self.setItem(row, col, None)
            del self._visible_rows[row]
        
    def scrollToRow(self, row):
        """滚动到指定行"""
        super().scrollToRow(row)
        self._update_visible_rows()
