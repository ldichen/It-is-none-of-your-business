"""
Author: DiChen
Date: 2025-07-30 23:18:09
LastEditors: DiChen
LastEditTime: 2025-07-31 03:00:00
"""

"""
模型执行管理模块
Author: DiChen
Date: 2025-07-30
"""

import subprocess
from typing import List, Union, Optional, Callable
from ..config.settings import MODEL_OUTPUT_DIR
from ..files.handler import FileHandler, OutputCollector
from ..utils.logger import get_logger

# 初始化日志
logger = get_logger(__name__)


class ModelExecutor:
    """模型执行器"""

    def __init__(self, output_dir: str = None):
        if output_dir is None:
            output_dir = MODEL_OUTPUT_DIR
        self.output_dir = output_dir
        self.file_handler = FileHandler()
        self.output_collector = OutputCollector()

    def execute_command(self, cmd: List[str]) -> Union[List[str], str, None]:
        """执行模型命令"""
        try:
            # 步骤1: 清理之前的模型输出（避免文件混淆）
            self.file_handler.cleanup_directory(self.output_dir)

            logger.info("执行命令: %s", ' '.join(cmd))

            # 执行命令
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd="./",
                timeout=3600,  # 超时时间（秒）
            )

            # 检查执行结果
            if result.returncode != 0:
                error_msg = f"命令执行失败\\n命令: {' '.join(cmd)}\\n返回码: {result.returncode}\\n错误信息: {result.stderr}"
                raise Exception(error_msg)

            logger.info("模型执行成功")
            if result.stdout:
                logger.debug("命令输出: %s", result.stdout)

            # 步骤3: 收集模型输出文件
            output_files = self.collect_outputs()

            # 返回输出文件路径
            if len(output_files) == 0:
                return None
            elif len(output_files) == 1:
                return output_files[0]
            else:
                return output_files

        except Exception as e:
            # 出错时清理模型输出目录
            self.file_handler.cleanup_directory(self.output_dir)
            raise Exception(f"模型执行失败: {str(e)}")

    def collect_outputs(self) -> List[Optional[str]]:
        """收集模型输出文件（需要在子类中实现具体逻辑）"""
        # 这个方法需要访问配置信息，在GradioService中会被重写
        return []


class ModelServiceHandler:
    """模型服务处理器"""

    def __init__(self):
        self.user_handler: Optional[Callable] = None
        self.model_executor: Optional[ModelExecutor] = None

    def set_user_handler(self, handler: Callable):
        """设置用户定义的模型处理函数"""
        self.user_handler = handler

    def set_executor(self, executor: ModelExecutor):
        """设置模型执行器"""
        self.model_executor = executor

    def execute_model(self, *input_values) -> Union[List[str], str, None]:
        """执行模型处理流程"""
        if not self.user_handler:
            raise RuntimeError(
                "未找到用户定义的模型处理函数，请确保使用@your_turn装饰器"
            )

        if not self.model_executor:
            raise RuntimeError("模型执行器未初始化")

        # 调用用户定义的模型处理函数获取命令
        cmd = self.user_handler(*input_values)

        # 执行模型命令
        return self.model_executor.execute_command(cmd)
