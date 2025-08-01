"""
Docker镜像管理器
"""

from typing import Optional, List, Dict, Any
from .config import DockerConfig
from ..utils.logger import get_logger

try:
    import docker
except ImportError:
    raise ImportError("Docker库未安装，请运行: pip install docker>=7.0.0")

logger = get_logger(__name__)

class DockerManager:
    """Docker镜像推送和管理器"""
    
    def __init__(self):
        self.config = DockerConfig()
        self.local_client = docker.from_env()
        self._remote_client = None
    
    def get_remote_client(self):
        """获取远程Docker客户端"""
        if self._remote_client is None:
            docker_host = self.config.get_docker_host()
            try:
                self._remote_client = docker.DockerClient(base_url=docker_host)
                # 测试连接
                self._remote_client.ping()
            except Exception as e:
                logger.error(f"无法连接到远程Docker服务器 {docker_host}: {e}")
                raise Exception(f"无法连接到远程Docker服务器: {e}")
        
        return self._remote_client
    
    def get_latest_image(self) -> Optional[str]:
        """获取最新构建的inoyb镜像"""
        try:
            images = self.local_client.images.list()
            inoyb_images = []
            
            for image in images:
                for tag in image.tags:
                    if tag.startswith('inoyb/'):
                        inoyb_images.append({
                            'name': tag,
                            'created': image.attrs['Created']
                        })
            
            if not inoyb_images:
                return None
            
            # 按创建时间排序，返回最新的
            latest = sorted(inoyb_images, key=lambda x: x['created'], reverse=True)[0]
            return latest['name']
        
        except Exception as e:
            logger.error(f"获取最新镜像失败: {e}")
            return None
    
    def push_image(self, image_name: Optional[str] = None) -> bool:
        """推送镜像到远程服务器
        
        Args:
            image_name: 镜像名称，如果为None则推送最新镜像
        
        Returns:
            bool: 推送是否成功
        """
        try:
            # 确定要推送的镜像
            if image_name is None:
                image_name = self.get_latest_image()
                if image_name is None:
                    logger.error("没有找到可推送的镜像")
                    return False
                logger.info(f"使用最新镜像: {image_name}")
            
            # 检查本地镜像是否存在
            try:
                local_image = self.local_client.images.get(image_name)
            except docker.errors.ImageNotFound:
                logger.error(f"本地镜像不存在: {image_name}")
                return False
            
            # 提醒用户当前使用的服务器
            if not self.config.is_using_default_server():
                current_server = self.config.get_docker_host()
                logger.warning(f"⚠️  当前使用个人远程服务器: {current_server}")
                logger.info("如需切换回默认服务器，请使用: inoyb config set default")
            
            # 获取远程客户端（用于连接验证）
            self.get_remote_client()
            
            # 准备远程标签
            registry = self.config.get_registry()
            remote_tag = f"{registry}/{image_name.replace('inoyb/', '')}"
            
            logger.info(f"开始推送镜像: {image_name} -> {remote_tag}")
            
            # 给本地镜像打远程标签
            local_image.tag(remote_tag)
            
            # 推送镜像
            push_logs = self.local_client.images.push(
                remote_tag,
                stream=True,
                decode=True
            )
            
            # 输出推送日志
            for log in push_logs:
                if 'status' in log:
                    if 'progress' in log:
                        logger.info(f"{log['status']}: {log.get('progress', '')}")
                    else:
                        logger.info(log['status'])
                
                if 'error' in log:
                    logger.error(f"推送失败: {log['error']}")
                    return False
            
            logger.info(f"镜像推送成功: {remote_tag}")
            
            # 自动清理本地旧镜像（如果启用）
            cleanup_settings = self.config.get_cleanup_settings()
            if cleanup_settings.get('auto_cleanup', False):
                from .builder import DockerBuilder
                builder = DockerBuilder()
                removed = builder.cleanup_old_images(cleanup_settings.get('keep_images', 3))
                if removed > 0:
                    logger.info(f"自动清理了 {removed} 个旧镜像")
            
            return True
            
        except Exception as e:
            logger.error(f"推送镜像失败: {e}")
            return False
    
    def list_remote_images(self) -> List[Dict[str, Any]]:
        """列出远程服务器上的镜像（如果支持）"""
        try:
            remote_client = self.get_remote_client()
            images = remote_client.images.list()
            
            inoyb_images = []
            registry = self.config.get_registry()
            
            for image in images:
                for tag in image.tags or []:
                    if registry in tag:
                        inoyb_images.append({
                            'name': tag,
                            'id': image.id[:12],
                            'created': image.attrs.get('Created', ''),
                            'size': image.attrs.get('Size', 0)
                        })
            
            return sorted(inoyb_images, key=lambda x: x['created'], reverse=True)
            
        except Exception as e:
            logger.error(f"获取远程镜像列表失败: {e}")
            return []
    
    def pull_and_run(self, image_name: str, port: int = 7860) -> bool:
        """拉取并运行镜像"""
        try:
            remote_client = self.get_remote_client()
            
            # 拉取镜像
            logger.info(f"拉取镜像: {image_name}")
            remote_client.images.pull(image_name)
            
            # 运行容器
            container_name = f"inoyb-{image_name.split('/')[-1]}"
            
            container = remote_client.containers.run(
                image_name,
                ports={f'{port}/tcp': port},
                detach=True,
                name=container_name,
                restart_policy={"Name": "unless-stopped"}
            )
            
            logger.info(f"容器启动成功: {container_name} (ID: {container.id[:12]})")
            logger.info(f"访问地址: http://<server-ip>:{port}")
            
            return True
            
        except Exception as e:
            logger.error(f"拉取并运行镜像失败: {e}")
            return False