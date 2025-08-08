"""
本地运行器 - 启动当前目录的gogogo.py
"""

import os
import sys
import signal
import socket
import subprocess
import webbrowser
from pathlib import Path
from typing import Optional

from ..utils.logger import get_logger
from ..docker.builder import DockerBuilder

logger = get_logger(__name__)


class LocalRunner:
    """本地运行器"""

    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """设置信号处理器"""
        def signal_handler(signum, frame):
            logger.info("收到退出信号，正在停止服务...")
            self.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def _find_free_port(self, start_port: int = 7860, max_attempts: int = 100) -> int:
        """查找可用端口"""
        for port in range(start_port, start_port + max_attempts):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('localhost', port))
                    return port
            except OSError:
                continue
        raise Exception(f"无法找到可用端口（尝试范围: {start_port}-{start_port + max_attempts}）")

    def validate_project(self, project_path: Path = None) -> tuple:
        """验证项目结构"""
        if project_path is None:
            project_path = Path(".")

        project_path = project_path.resolve()

        # 检查gogogo.py是否存在
        gogogo_path = project_path / "gogogo.py"
        if not gogogo_path.exists():
            raise FileNotFoundError(
                f"❌ 当前目录没有找到gogogo.py\\n"
                f"   请确保在inoyb项目根目录下运行此命令\\n"
                f"   当前目录: {project_path}"
            )

        # 使用DockerBuilder验证完整项目结构
        try:
            builder = DockerBuilder()
            mc_config, has_examples = builder.validate_project(str(project_path))
            model_name = mc_config["model_info"]["name"]
            return mc_config, has_examples, model_name
        except Exception as e:
            logger.warning(f"项目结构验证警告: {e}")
            # 即使验证失败，也允许运行（可能是简化的项目结构）
            return {}, False, "unknown-model"

    def _check_dependencies(self) -> bool:
        """检查Python依赖"""
        try:
            import gradio
            logger.info(f"✅ Gradio版本: {gradio.__version__}")
            return True
        except ImportError:
            logger.error("❌ Gradio未安装，请先安装依赖:")
            logger.error("   pip install gradio")
            return False

    def run(
        self,
        port: int = 7860,
        host: str = "0.0.0.0",
        reload: bool = False,
        open_browser: bool = False,
        verbose: bool = False,
        project_path: str = ".",
    ) -> None:
        """运行本地服务"""
        project_path = Path(project_path).resolve()

        logger.info("🚀 启动inoyb本地服务...")
        logger.info(f"   项目路径: {project_path}")

        # 1. 验证项目结构
        try:
            mc_config, has_examples, model_name = self.validate_project(project_path)
            logger.info(f"✅ 项目验证通过")
            logger.info(f"   模型名称: {model_name}")
            if has_examples:
                logger.info(f"   包含examples目录")
        except Exception as e:
            logger.error(str(e))
            sys.exit(1)

        # 2. 检查依赖
        if not self._check_dependencies():
            sys.exit(1)

        # 3. 端口处理
        original_port = port
        if port == 7860:
            # 自动查找可用端口
            try:
                port = self._find_free_port(port)
                if port != original_port:
                    logger.info(f"💡 端口{original_port}被占用，自动使用端口{port}")
            except Exception as e:
                logger.error(f"❌ 端口分配失败: {e}")
                sys.exit(1)
        else:
            # 检查指定端口是否可用
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind((host, port))
            except OSError:
                logger.error(f"❌ 端口{port}被占用，请使用其他端口")
                sys.exit(1)

        # 4. 准备环境变量
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        
        # 设置Gradio相关环境变量
        env["GRADIO_SERVER_NAME"] = host
        env["GRADIO_SERVER_PORT"] = str(port)

        if verbose:
            env["GRADIO_DEBUG"] = "1"

        # 5. 启动进程
        logger.info("🔨 启动gogogo.py...")
        logger.info(f"   主机: {host}")
        logger.info(f"   端口: {port}")
        if reload:
            logger.info("   🔄 热重载模式已启用")

        try:
            if reload:
                self._run_with_reload(project_path, env)
            else:
                self._run_direct(project_path, env)

            # 6. 打开浏览器
            if open_browser:
                url = f"http://localhost:{port}"
                logger.info(f"🌐 正在打开浏览器: {url}")
                webbrowser.open(url)

            # 7. 服务启动成功提示
            url = f"http://{host}:{port}" if host != "0.0.0.0" else f"http://localhost:{port}"
            logger.info(f"✅ 服务启动成功!")
            logger.info(f"   🌍 访问地址: {url}")
            logger.info(f"   📋 按Ctrl+C停止服务")

            # 8. 等待进程结束
            if self.process:
                self.process.wait()

        except KeyboardInterrupt:
            logger.info("\\n👋 收到停止信号...")
            self.stop()
        except Exception as e:
            logger.error(f"❌ 启动失败: {e}")
            sys.exit(1)

    def _run_direct(self, project_path: Path, env: dict):
        """直接运行模式"""
        gogogo_path = project_path / "gogogo.py"
        
        self.process = subprocess.Popen(
            [sys.executable, str(gogogo_path)],
            cwd=str(project_path),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )

        # 实时输出日志
        self._stream_output()

    def _run_with_reload(self, project_path: Path, env: dict):
        """热重载模式（简化版本）"""
        logger.info("💡 热重载功能开发中，当前使用直接运行模式")
        self._run_direct(project_path, env)

    def _stream_output(self):
        """实时输出子进程的日志"""
        if not self.process or not self.process.stdout:
            return

        try:
            for line in iter(self.process.stdout.readline, ''):
                if line:
                    # 移除末尾换行符并输出
                    print(line.rstrip())
                    sys.stdout.flush()
        except Exception as e:
            logger.error(f"日志输出异常: {e}")

    def stop(self):
        """停止服务"""
        if self.process and self.process.poll() is None:
            logger.info("🛑 正在停止服务...")
            
            # 尝试优雅停止
            self.process.terminate()
            
            # 等待最多5秒
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("强制停止服务...")
                self.process.kill()
                
            logger.info("✅ 服务已停止")