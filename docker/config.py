"""
Author: DiChen
Date: 2025-08-01 15:05:00
LastEditors: DiChen
LastEditTime: 2025-08-01 16:16:36
"""

"""
Docker配置管理
"""

import json
from pathlib import Path
from typing import Dict, Any


class DockerConfig:
    """Docker配置管理器"""

    def __init__(self):
        self.config_dir = Path.home() / ".inoyb"
        self.config_file = self.config_dir / "config.json"
        self._ensure_config_dir()
        self._load_config()

    def _ensure_config_dir(self):
        """确保配置目录存在"""
        self.config_dir.mkdir(exist_ok=True)

    def _load_config(self):
        """加载配置文件"""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
            except Exception:
                self.config = self._default_config()
        else:
            self.config = self._default_config()

    def _default_config(self) -> Dict[str, Any]:
        """默认配置"""
        return {
            "docker": {
                "default_server": "tcp://docker.inoyb.com:2376",
                "current_server": None,
                "registries": {"default": "registry.inoyb.com/inoyb"},
                "cleanup": {"keep_images": 3, "auto_cleanup": True},
                "base_images": {
                    "registry_mirror": None,  # 镜像加速地址
                    "custom_mappings": {},    # 自定义镜像映射
                    "default_registry": None # 默认镜像仓库前缀
                }
            }
        }

    def save_config(self):
        """保存配置到文件"""
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)

    def get_docker_host(self) -> str:
        """获取当前Docker服务器地址"""
        current = self.config["docker"].get("current_server")
        if current:
            return current
        return self.config["docker"]["default_server"]

    def set_docker_host(self, host: str):
        """设置Docker服务器地址"""
        self.config["docker"]["current_server"] = host
        self.save_config()

    def set_default_server(self):
        """切换回默认服务器"""
        self.config["docker"]["current_server"] = None
        self.save_config()

    def is_using_default_server(self) -> bool:
        """检查是否使用默认服务器"""
        return self.config["docker"].get("current_server") is None

    def get_registry(self) -> str:
        """获取镜像仓库地址"""
        return self.config["docker"]["registries"]["default"]

    def get_cleanup_settings(self) -> Dict[str, Any]:
        """获取清理设置"""
        return self.config["docker"]["cleanup"]

    def get_base_image_config(self) -> Dict[str, Any]:
        """获取基础镜像配置"""
        return self.config["docker"].get("base_images", {})

    def set_registry_mirror(self, mirror: str):
        """设置镜像加速地址"""
        if "base_images" not in self.config["docker"]:
            self.config["docker"]["base_images"] = {}
        self.config["docker"]["base_images"]["registry_mirror"] = mirror
        self.save_config()

    def set_default_registry(self, registry: str):
        """设置默认镜像仓库前缀"""
        if "base_images" not in self.config["docker"]:
            self.config["docker"]["base_images"] = {}
        self.config["docker"]["base_images"]["default_registry"] = registry
        self.save_config()

    def add_image_mapping(self, original: str, replacement: str):
        """添加自定义镜像映射"""
        if "base_images" not in self.config["docker"]:
            self.config["docker"]["base_images"] = {}
        if "custom_mappings" not in self.config["docker"]["base_images"]:
            self.config["docker"]["base_images"]["custom_mappings"] = {}
        
        self.config["docker"]["base_images"]["custom_mappings"][original] = replacement
        self.save_config()

    def resolve_base_image(self, image: str, cli_registry: str = None, cli_base_image: str = None) -> str:
        """解析基础镜像地址，支持多层级配置
        
        优先级：CLI参数 > 项目配置 > 用户配置 > 默认值
        """
        # 1. CLI直接指定完整镜像名
        if cli_base_image:
            return cli_base_image
        
        # 2. 检查自定义映射
        base_config = self.get_base_image_config()
        custom_mappings = base_config.get("custom_mappings", {})
        if image in custom_mappings:
            return custom_mappings[image]
        
        # 3. CLI指定仓库前缀
        if cli_registry:
            if cli_registry.endswith('/'):
                return f"{cli_registry}{image}"
            else:
                return f"{cli_registry}/{image}"
        
        # 4. 用户配置的默认仓库
        default_registry = base_config.get("default_registry")
        if default_registry:
            if default_registry.endswith('/'):
                return f"{default_registry}{image}"
            else:
                return f"{default_registry}/{image}"
        
        # 5. 镜像加速（仅对官方镜像）
        registry_mirror = base_config.get("registry_mirror")
        if registry_mirror and not '/' in image.split(':')[0]:
            # 官方镜像，使用加速
            if registry_mirror.endswith('/'):
                return f"{registry_mirror}library/{image}"
            else:
                return f"{registry_mirror}/library/{image}"
        
        # 6. 返回原始镜像名
        return image

    def load_project_config(self, project_path: str) -> Dict[str, Any]:
        """加载项目级Docker配置"""
        project_config_path = Path(project_path) / ".inoyb" / "docker.json"
        if project_config_path.exists():
            try:
                with open(project_config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def resolve_base_image_with_project(self, image: str, project_path: str = ".", 
                                      cli_registry: str = None, cli_base_image: str = None) -> str:
        """解析基础镜像地址，包含项目配置支持
        
        优先级：CLI参数 > 项目配置 > 用户配置 > 默认值
        """
        # 1. CLI直接指定完整镜像名
        if cli_base_image:
            return cli_base_image
        
        # 2. 加载项目配置
        project_config = self.load_project_config(project_path)
        project_base_image = project_config.get("base_image")
        if project_base_image:
            return project_base_image
        
        # 3. CLI指定仓库前缀
        if cli_registry:
            if cli_registry.endswith('/'):
                return f"{cli_registry}{image}"
            else:
                return f"{cli_registry}/{image}"
        
        # 4. 项目配置的仓库前缀
        project_registry = project_config.get("registry")
        if project_registry:
            if project_registry.endswith('/'):
                return f"{project_registry}{image}"
            else:
                return f"{project_registry}/{image}"
        
        # 5. 用户配置和默认处理
        return self.resolve_base_image(image, None, None)
