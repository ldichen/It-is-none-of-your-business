"""
Author: DiChen
Date: 2025-07-30 23:19:33
LastEditors: DiChen
LastEditTime: 2025-07-31 02:57:39
"""

"""
iinoyb - 基于mc.json配置的Gradio模型服务框架
Author: DiChen
Date: 2025-07-30
"""

import functools
from typing import Callable, Optional
from .core.service import GradioService
from .config.settings import validate_project_structure
from .utils.logger import get_logger, InoyBLogger

# 初始化日志系统
InoyBLogger.setup_logging()
logger = get_logger(__name__)


def your_turn(
    mc_json: str = "mc.json",
    port: Optional[int] = None,
    example_path: Optional[str] = None,
    output_dir: Optional[str] = None,
):
    """
    装饰器：将用户的模型处理函数包装成完整的Gradio服务

    Args:
        mc_json: mc.json配置文件路径（必选）
        port: Gradio服务端口，默认从环境变量读取
        example_path: 示例数据路径，默认从环境变量读取
        output_dir: 模型输出目录，默认从环境变量读取
    """

    def decorator(user_handler: Callable):
        @functools.wraps(user_handler)
        def wrapper(*args, **kwargs):
            # 正常调用用户函数
            return user_handler(*args, **kwargs)

        def run():
            """启动Gradio服务"""
            logger.info("启动iinoyb模型服务框架...")

            # 检查项目结构
            if not validate_project_structure():
                logger.error("项目结构检查失败，程序退出")
                return

            # 创建服务实例
            service = GradioService()

            try:
                # 设置服务参数并加载配置
                config = service.setup(
                    config_path=mc_json,
                    user_handler=wrapper,
                    port=port,
                    example_path=example_path,
                    output_dir=output_dir,
                )

                logger.info("配置加载成功，创建Gradio界面...")

                # 创建并启动Gradio界面
                demo = service.create_interface(config)

                logger.info("启动Web服务，端口: %s", service.server_port)
                service.launch(demo)

            except Exception as e:
                logger.error("服务启动失败: %s", str(e))
                return

        # 给装饰后的函数添加run方法
        wrapper.run = run
        return wrapper

    return decorator


__all__ = ["your_turn"]
