"""
Author: DiChen
Date: 2025-07-31 12:54:13
LastEditors: DiChen
LastEditTime: 2025-07-31 13:15:34
"""

"""
全局配置设置模块
Author: DiChen
Date: 2025-07-30

统一管理所有配置变量，优先级：默认值 → 环境变量 → 用户参数
"""

import os
from ..utils.logger import get_logger

# 初始化日志
logger = get_logger(__name__)

# 全局配置变量
GRADIO_SERVER_PORT = int(os.getenv("GRADIO_SERVER_PORT", "7860"))
EXAMPLE_DATA_PATH = os.getenv("EXAMPLE_DATA_PATH", "examples")
MODEL_OUTPUT_DIR = os.getenv("MODEL_OUTPUT_DIR", "outputs")


def validate_project_structure():
    """
    检查当前工作目录是否为有效的项目根目录
    必须包含：
    1. gogogo.py 文件
    2. model 文件夹

    Returns:
        bool: 如果项目结构有效返回 True，否则返回 False
    """
    current_dir = os.getcwd()

    # 检查必需的文件和目录
    gogogo_exists = os.path.exists("gogogo.py")
    model_dir_exists = os.path.exists("model") and os.path.isdir("model")

    if not gogogo_exists:
        logger.error("在当前目录 '%s' 中找不到 'gogogo.py' 文件", current_dir)
        logger.info("请确保从项目根目录启动程序")
        return False

    if not model_dir_exists:
        logger.error("在当前目录 '%s' 中找不到 'model' 文件夹", current_dir)
        logger.info("请确保从项目根目录启动程序")
        return False

    logger.info("项目结构检查通过，当前目录：%s", current_dir)
    return True
