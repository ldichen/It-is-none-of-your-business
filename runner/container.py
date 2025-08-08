"""
容器运行器 - 启动Docker镜像
"""

import sys
import signal
from typing import Optional, Dict, Any

from ..utils.logger import get_logger

try:
    import docker
except ImportError:
    docker = None

logger = get_logger(__name__)


class ContainerRunner:
    """容器运行器"""

    def __init__(self):
        if docker is None:
            raise ImportError("Docker库未安装，请运行: pip install docker>=7.0.0")
        
        try:
            self.client = docker.from_env()
            self.client.ping()
        except Exception as e:
            raise Exception(f"无法连接到Docker服务: {e}")
        
        self.container: Optional[Any] = None
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """设置信号处理器"""
        def signal_handler(signum, frame):
            logger.info("收到退出信号，正在停止容器...")
            self.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def _check_image_exists(self, image_name: str) -> bool:
        """检查镜像是否存在"""
        try:
            self.client.images.get(image_name)
            return True
        except docker.errors.ImageNotFound:
            return False
        except Exception as e:
            logger.error(f"检查镜像时出错: {e}")
            return False

    def _format_port_mapping(self, port: int) -> Dict[str, int]:
        """格式化端口映射"""
        return {7860: port}

    def _format_environment(self, env_vars: Dict[str, str]) -> Dict[str, str]:
        """格式化环境变量"""
        return env_vars or {}

    def _format_volumes(self, volumes: Dict[str, str]) -> Dict[str, Dict[str, str]]:
        """格式化卷挂载"""
        if not volumes:
            return {}
        
        formatted_volumes = {}
        for host_path, container_path in volumes.items():
            formatted_volumes[host_path] = {'bind': container_path, 'mode': 'rw'}
        return formatted_volumes

    def run(
        self,
        image_name: str,
        port: int = 7860,
        daemon: bool = False,
        remove: bool = True,
        interactive: bool = False,
        name: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        volumes: Optional[Dict[str, str]] = None,
        follow_logs: bool = True,
    ) -> None:
        """运行Docker镜像"""
        
        logger.info(f"🚀 启动Docker容器...")
        logger.info(f"   镜像: {image_name}")

        # 1. 检查镜像是否存在
        if not self._check_image_exists(image_name):
            logger.error(f"❌ 镜像不存在: {image_name}")
            logger.info("💡 可用的解决方案:")
            logger.info("   1. 检查镜像名称是否正确")
            logger.info("   2. 运行 inoyb images list 查看本地镜像")
            logger.info("   3. 运行 inoyb build 构建镜像")
            sys.exit(1)

        # 2. 准备运行参数
        run_kwargs = {
            'image': image_name,
            'ports': self._format_port_mapping(port),
            'environment': self._format_environment(env),
            'volumes': self._format_volumes(volumes),
            'remove': remove,
            'detach': daemon or not follow_logs,  # 如果不需要跟踪日志，则分离运行
        }

        if name:
            run_kwargs['name'] = name

        if interactive:
            run_kwargs['stdin_open'] = True
            run_kwargs['tty'] = True

        # 3. 启动容器
        logger.info(f"   端口映射: 7860 -> {port}")
        if env:
            logger.info(f"   环境变量: {len(env)} 个")
        if volumes:
            logger.info(f"   卷挂载: {len(volumes)} 个")

        try:
            self.container = self.client.containers.run(**run_kwargs)
            
            if daemon:
                # 后台模式
                logger.info(f"✅ 容器启动成功 (后台运行)!")
                logger.info(f"   容器ID: {self.container.id[:12]}")
                logger.info(f"   🌍 访问地址: http://localhost:{port}")
                logger.info(f"   📋 查看日志: docker logs {self.container.id[:12]}")
                logger.info(f"   🛑 停止容器: docker stop {self.container.id[:12]}")
                
            elif follow_logs:
                # 前台模式，跟踪日志
                logger.info(f"✅ 容器启动成功!")
                logger.info(f"   容器ID: {self.container.id[:12]}")
                logger.info(f"   🌍 访问地址: http://localhost:{port}")
                logger.info(f"   📋 按Ctrl+C停止容器\\n")
                
                # 实时显示容器日志
                self._stream_logs()
                
            else:
                # 分离模式但不是daemon
                logger.info(f"✅ 容器启动成功!")
                logger.info(f"   容器ID: {self.container.id[:12]}")
                logger.info(f"   🌍 访问地址: http://localhost:{port}")

        except docker.errors.APIError as e:
            if "port is already allocated" in str(e):
                logger.error(f"❌ 端口{port}被占用")
                logger.info("💡 解决方案:")
                logger.info(f"   使用其他端口: inoyb run {image_name} --port 8080")
            else:
                logger.error(f"❌ 容器启动失败: {e}")
            sys.exit(1)
            
        except Exception as e:
            logger.error(f"❌ 意外错误: {e}")
            sys.exit(1)

    def _stream_logs(self):
        """实时显示容器日志"""
        if not self.container:
            return

        try:
            # 跟踪日志输出
            for log_line in self.container.logs(stream=True, follow=True):
                try:
                    # 解码日志行
                    line = log_line.decode('utf-8').rstrip()
                    if line:
                        print(line)
                        sys.stdout.flush()
                except UnicodeDecodeError:
                    # 处理无法解码的字节
                    continue
                    
        except KeyboardInterrupt:
            logger.info("\\n👋 收到停止信号...")
            self.stop()
        except Exception as e:
            logger.error(f"日志跟踪异常: {e}")

    def stop(self):
        """停止容器"""
        if self.container:
            try:
                logger.info("🛑 正在停止容器...")
                
                # 检查容器状态
                self.container.reload()
                if self.container.status == 'running':
                    self.container.stop(timeout=10)
                    logger.info("✅ 容器已停止")
                else:
                    logger.info("ℹ️  容器已经停止")
                    
            except Exception as e:
                logger.error(f"停止容器时出错: {e}")

    def list_running_containers(self) -> list:
        """列出正在运行的inoyb容器"""
        try:
            containers = self.client.containers.list(
                filters={'ancestor': 'inoyb'}  # 筛选inoyb镜像的容器
            )
            
            container_info = []
            for container in containers:
                info = {
                    'id': container.id[:12],
                    'name': container.name,
                    'image': container.image.tags[0] if container.image.tags else container.image.id[:12],
                    'status': container.status,
                    'ports': container.ports,
                    'created': container.attrs['Created']
                }
                container_info.append(info)
                
            return container_info
            
        except Exception as e:
            logger.error(f"获取容器列表失败: {e}")
            return []