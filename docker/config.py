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
