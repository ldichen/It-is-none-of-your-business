"""
Gradio服务核心管理模块
Author: DiChen
Date: 2025-07-30
"""

import os
import signal
import sys
import gradio as gr
from typing import List, Optional, Dict, Any

from ..config.manager import ConfigManager
from ..config.settings import GRADIO_SERVER_PORT, EXAMPLE_DATA_PATH, MODEL_OUTPUT_DIR
from ..ui.components import UIComponentFactory, UILayoutManager
from ..execution.executor import ModelExecutor, ModelServiceHandler
from ..files.handler import FolderBrowserGenerator
from ..utils.preview import PreviewGenerator
from ..utils.isolated_executor import IsolatedModelExecutor
from ..utils.logger import get_logger

# 初始化日志
logger = get_logger(__name__)


class GradioModelExecutor(ModelExecutor):
    """扩展的模型执行器，支持配置管理"""

    def __init__(self, config_manager: ConfigManager, output_dir: str = None):
        if output_dir is None:
            output_dir = MODEL_OUTPUT_DIR
        super().__init__(output_dir)
        self.config_manager = config_manager

    def collect_outputs(self) -> List[Optional[str]]:
        """收集模型输出文件"""
        config = self.config_manager.load_config()
        if not config or "outputs" not in config:
            logger.warning("无法获取mc.json输出配置")
            return []

        return self.output_collector.collect_outputs(self.output_dir, config["outputs"])


class GradioService:
    """Gradio服务管理器"""

    def __init__(self):
        self.config_manager = ConfigManager()
        self.component_factory = UIComponentFactory()
        self.layout_manager = UILayoutManager(self.component_factory)
        self.service_handler = ModelServiceHandler()
        self.folder_browser = FolderBrowserGenerator()
        self.preview_generator = PreviewGenerator()

        # 初始化隔离执行器
        self.isolated_executor = IsolatedModelExecutor(
            max_workers=5, large_file_threshold=200 * 1024 * 1024
        )

        # 启动时清空全局预览目录（用于向后兼容）和清理旧工作空间
        # 注意：现在主要使用隔离工作空间中的preview，全局目录主要用于向后兼容
        self.preview_generator.clear_preview_dir()
        self.isolated_executor.cleanup_old_workspaces(max_age_hours=24)

        # 使用全局配置变量
        self.server_port = GRADIO_SERVER_PORT
        self.example_path = EXAMPLE_DATA_PATH
        self.output_dir = MODEL_OUTPUT_DIR

    def setup(
        self,
        config_path: str,
        user_handler,
        port: Optional[int] = None,
        example_path: Optional[str] = None,
        output_dir: Optional[str] = None,
    ):
        """设置服务参数"""
        # 用户参数覆盖全局配置
        if port is not None:
            self.server_port = port
        if example_path is not None:
            self.example_path = example_path
        if output_dir is not None:
            self.output_dir = output_dir

        # 加载配置
        config = self.config_manager.load_config(config_path)
        if not config:
            raise ValueError(f"无法加载配置文件: {config_path}")

        # 设置模型执行器和处理器
        model_executor = GradioModelExecutor(self.config_manager, self.output_dir)
        self.service_handler.set_executor(model_executor)
        self.service_handler.set_user_handler(user_handler)

        return config

    def create_interface(self, config: Dict) -> gr.Blocks:
        """创建Gradio界面"""
        # 解析配置
        input_fields, output_fields = self.config_manager.parse_config(config)
        layout_type = self.component_factory.get_layout_type(
            len(input_fields), len(output_fields)
        )

        # 自定义主题和CSS
        custom_theme = gr.themes.Default(
            primary_hue="blue", secondary_hue="blue", neutral_hue="slate"
        )

        custom_css = """
        footer { display: none !important; }
        .gradio-container .footer { display: none !important; }
        .gradio-container .version { display: none !important; }
        .primary, .primary:hover, .primary:focus {
            background-color: #60a5fa !important;
            border-color: #60a5fa !important;
        }
        .btn-primary, .btn-primary:hover, .btn-primary:focus {
            background-color: #60a5fa !important;
            border-color: #60a5fa !important;
            color: white !important;
        }
        .progress-bar { background-color: #60a5fa !important; }
        a { color: #60a5fa !important; }
        .selected { background-color: #60a5fa !important; }
        """

        # 获取应用标题
        model_info = self.config_manager.get_model_info()
        app_title = model_info.get("name", "模型服务平台")

        with gr.Blocks(title=app_title, theme=custom_theme, css=custom_css) as demo:
            # 上部：模型信息区域
            self.layout_manager.create_model_info_section(model_info)
            gr.Markdown("---")  # 分隔线

            # 中部：输入输出区域
            input_components, output_components, preview_components = (
                self.layout_manager.create_layout(
                    input_fields, output_fields, layout_type
                )
            )

            # 执行按钮和状态显示
            with gr.Row():
                submit_btn = gr.Button("🚀 运行模型", variant="primary", size="lg")

            status_box = gr.Textbox(
                label="运行状态", interactive=False, visible=False, lines=3
            )

            # 绑定事件
            submit_btn.click(
                fn=self._model_execution_wrapper(
                    input_fields, output_fields, preview_components
                ),
                inputs=input_components,
                outputs=output_components + preview_components + [status_box],
            )

            gr.Markdown("---")  # 分隔线

            # 下部：示例数据区域
            self._create_examples_section(input_fields, input_components)

        return demo

    def _model_execution_wrapper(
        self,
        input_fields: List[Dict],
        output_fields: List[Dict],
        preview_components: List[Any],
    ):
        """模型执行包装器"""

        def wrapper(*input_values):
            # 检查输入参数数量
            if len(input_values) != len(input_fields):
                error_msg = f"❌ 输入参数数量不匹配：期望{len(input_fields)}个，实际{len(input_values)}个"
                return (
                    [None] * len(output_fields)
                    + [None] * len(preview_components)
                    + [gr.update(value=error_msg, visible=True)]
                )

            # 验证必填字段
            for field_info, value in zip(input_fields, input_values):
                if field_info["required"] and (value is None or value == ""):
                    error_msg = f"❌ 必填字段 '{field_info['field_name']}' 不能为空"
                    return (
                        [None] * len(output_fields)
                        + [None] * len(preview_components)
                        + [gr.update(value=error_msg, visible=True)]
                    )

            try:
                # 使用隔离执行器执行模型
                logger.info("开始并发模型执行...")

                # 构建命令模板（从用户handler获取）
                user_cmd = self.service_handler.user_handler(*input_values)
                if isinstance(user_cmd, (list, tuple)):
                    cmd_template = list(user_cmd)
                else:
                    cmd_template = None  # 使用默认模板

                # 在隔离工作空间中执行
                isolated_output_dir = self.isolated_executor.execute_model_isolated(
                    inputs=list(input_values), cmd_template=cmd_template
                )

                logger.info("隔离执行完成，输出目录: %s", isolated_output_dir)

                # 使用GradioModelExecutor收集输出文件（从隔离目录）
                original_output_dir = self.service_handler.model_executor.output_dir
                self.service_handler.model_executor.output_dir = isolated_output_dir

                try:
                    outputs = self.service_handler.model_executor.collect_outputs()
                finally:
                    # 恢复原始输出目录
                    self.service_handler.model_executor.output_dir = original_output_dir

                # 处理模型返回的文件路径
                output_files = []
                if isinstance(outputs, (list, tuple)):
                    output_files = list(outputs)
                elif outputs is not None:
                    output_files = [outputs]

                # 处理不同类型的输出（参数、文件、文件夹）
                processed_outputs = []
                preview_updates = []

                for i, (output, field_info) in enumerate(
                    zip(output_files, output_fields)
                ):
                    field_type = field_info.get("type", "file")

                    if field_type == "param":
                        # 参数类型：直接传递值给Gradio组件
                        processed_outputs.append(output)
                        # 参数类型不生成预览
                        preview_updates.append(gr.update(visible=False))
                    elif (
                        output
                        and isinstance(output, str)
                        and output.startswith("FOLDER_BROWSER:")
                    ):
                        # 文件夹浏览器模式
                        folder_path = output.replace("FOLDER_BROWSER:", "")
                        field_name = field_info["field_name"]
                        html_content = self.folder_browser.generate_html(
                            folder_path, field_name
                        )
                        processed_outputs.append(gr.update(value=html_content))
                        # 文件夹类型不生成预览
                        preview_updates.append(gr.update(visible=False))
                    else:
                        # 文件类型
                        if output and os.path.exists(str(output)):
                            # 对于存在的文件，确保使用正确的格式以支持下载
                            processed_outputs.append(output)

                            # 只对 geodata 类型生成预览
                            if field_info.get("type") == "geodata":
                                # 获取bands配置
                                bands_config = field_info.get("bands", [3, 2, 1])
                                # 生成preview（在隔离工作空间中）
                                preview_path = self.preview_generator.generate_preview(
                                    str(output),
                                    bands_config=bands_config,
                                    workspace_dir=isolated_output_dir,
                                )
                                if preview_path and os.path.exists(preview_path):
                                    preview_updates.append(
                                        gr.update(value=preview_path, visible=True)
                                    )
                                else:
                                    preview_updates.append(gr.update(visible=False))
                            else:
                                preview_updates.append(gr.update(visible=False))
                        else:
                            processed_outputs.append(output)
                            preview_updates.append(gr.update(visible=False))

                # 补齐输出长度
                while len(processed_outputs) < len(output_fields):
                    processed_outputs.append(None)
                while len(preview_updates) < len(preview_components):
                    preview_updates.append(gr.update(visible=False))

                return (
                    processed_outputs
                    + preview_updates
                    + [gr.update(value="✅ 模型运行完成！", visible=True)]
                )

            except Exception as e:
                error_msg = f"❌ 模型运行失败：{str(e)}"
                logger.error("模型运行过程中发生错误: %s", str(e))

                # 执行失败时清空全局预览目录（隔离工作空间会自动清理）
                self.preview_generator.clear_preview_dir()

                # 失败时隐藏所有输出组件
                failed_outputs = [None] * len(output_fields)
                failed_previews = [gr.update(visible=False)] * len(preview_components)

                return (
                    failed_outputs
                    + failed_previews
                    + [gr.update(value=error_msg, visible=True)]
                )

        return wrapper

    def _setup_signal_handlers(self):
        """设置信号处理程序"""

        def signal_handler(signum, frame):
            logger.info("接收到停止信号，服务正在关闭...")
            # 关闭隔离执行器
            self.isolated_executor.shutdown()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def _create_examples_section(
        self, input_fields: List[Dict], input_components: List[Any]
    ):
        """创建示例数据区域"""
        gr.Markdown("### 📋 示例数据")

        examples_list = []
        for field_info in input_fields:
            example_file = self.config_manager.find_example_file(
                field_info["field_name"], self.example_path
            )
            examples_list.append(example_file)

        if examples_list and any(examples_list):
            gr.Examples(
                examples=[examples_list],
                inputs=input_components,
                label="点击使用示例数据",
            )
        else:
            gr.Markdown("*暂无可用的示例数据*")

    def launch(self, demo: gr.Blocks):
        """启动Gradio服务"""
        # 设置信号处理程序
        self._setup_signal_handlers()

        logger.info("启动Gradio服务，端口: %s", self.server_port)

        # 启动参数
        launch_params = {
            "server_name": "0.0.0.0",
            "server_port": self.server_port,
            "share": False,
            "inbrowser": False,
            "show_error": True,
            "quiet": False,
        }

        # 检查favicon文件
        favicon_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "static", "favicon.ico"
        )
        if os.path.exists(favicon_path):
            launch_params["favicon_path"] = favicon_path

        try:
            # 启用Gradio队列支持并发
            logger.info("启用Gradio队列支持并发...")
            demo.queue(
                max_size=50, default_concurrency_limit=5
            )  # 队列最大50个请求，默认并发5个

            demo.launch(**launch_params)
            logger.info("服务已成功启动！")
            logger.info("访问地址: http://127.0.0.1:%s", self.server_port)
            logger.info("局域网访问: http://0.0.0.0:%s", self.server_port)
            logger.info("并发支持已启用")
            logger.info("  - 队列最大容量: 50个请求")
            logger.info("  - 默认并发限制: 5个同时执行")
            logger.info("  - 智能工作空间隔离: 已启用")

        except KeyboardInterrupt:
            logger.info("服务已停止")
            sys.exit(0)
        except Exception as e:
            logger.warning("启动时出现异常（但服务可能已正常启动）: %s", str(e))
            logger.info("请尝试访问: http://127.0.0.1:%s", self.server_port)
            logger.info("如果无法访问，请检查端口是否被占用或防火墙设置")
