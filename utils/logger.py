"""
统一日志配置模块
Author: DiChen
Date: 2024-01-31
"""

import logging
import sys
from typing import Optional


class ColoredFormatter(logging.Formatter):
    """带颜色的日志格式化器"""
    
    # 颜色代码
    COLORS = {
        'DEBUG': '\033[36m',    # 青色
        'INFO': '\033[32m',     # 绿色
        'WARNING': '\033[33m',  # 黄色
        'ERROR': '\033[31m',    # 红色
        'CRITICAL': '\033[35m', # 紫色
    }
    RESET = '\033[0m'
    
    # Emoji 映射
    EMOJIS = {
        'DEBUG': '🔍',
        'INFO': '✅',
        'WARNING': '⚠️',
        'ERROR': '❌',
        'CRITICAL': '🚨',
    }
    
    def format(self, record):
        # 获取原始消息
        message = super().format(record)
        
        # 添加颜色和emoji
        level_name = record.levelname
        color = self.COLORS.get(level_name, '')
        emoji = self.EMOJIS.get(level_name, '')
        
        # 格式：[时间] EMOJI LEVEL: 消息
        if color:
            return f"{color}{emoji} {level_name}: {message}{self.RESET}"
        else:
            return f"{emoji} {level_name}: {message}"


class InoyBLogger:
    """inoyb框架统一日志管理器"""
    
    _initialized = False
    _loggers = {}
    
    @classmethod
    def setup_logging(cls, level: str = "INFO", enable_colors: bool = True):
        """
        设置全局日志配置
        
        Args:
            level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            enable_colors: 是否启用彩色输出
        """
        if cls._initialized:
            return
        
        # 转换日志级别
        numeric_level = getattr(logging, level.upper(), logging.INFO)
        
        # 创建根logger
        root_logger = logging.getLogger('inoyb')
        root_logger.setLevel(numeric_level)
        
        # 避免重复添加handler
        if root_logger.handlers:
            return
        
        # 创建控制台handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        
        # 设置格式化器
        if enable_colors:
            formatter = ColoredFormatter(
                fmt='[%(asctime)s] %(message)s',
                datefmt='%H:%M:%S'
            )
        else:
            formatter = logging.Formatter(
                fmt='[%(asctime)s] %(levelname)s: %(message)s',
                datefmt='%H:%M:%S'
            )
        
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        
        # 防止重复初始化
        cls._initialized = True
    
    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """
        获取模块专用logger
        
        Args:
            name: logger名称，通常使用 __name__
            
        Returns:
            Logger实例
        """
        # 确保日志系统已初始化
        if not cls._initialized:
            cls.setup_logging()
        
        # 使用缓存避免重复创建
        if name in cls._loggers:
            return cls._loggers[name]
        
        # 创建子logger
        logger = logging.getLogger(f'inoyb.{name}')
        cls._loggers[name] = logger
        
        return logger


# 便捷函数
def get_logger(name: str) -> logging.Logger:
    """获取logger的便捷函数"""
    return InoyBLogger.get_logger(name)


# 模块级别的logger（供框架内部使用）
framework_logger = get_logger('framework')


# 日志级别辅助函数
def set_log_level(level: str):
    """动态设置日志级别"""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.getLogger('inoyb').setLevel(numeric_level)
    
    # 更新所有handler的级别
    for handler in logging.getLogger('inoyb').handlers:
        handler.setLevel(numeric_level)