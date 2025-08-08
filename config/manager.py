"""
配置管理模块
Author: DiChen
Date: 2025-07-30
"""

import os
import json
from typing import Dict, List, Tuple, Optional
from ..utils.logger import get_logger

# 初始化日志
logger = get_logger(__name__)


class ConfigManager:
    """mc.json配置文件管理器"""
    
    def __init__(self):
        self._config = None
        self._config_path = "mc.json"
    
    def load_config(self, config_path: Optional[str] = None) -> Optional[Dict]:
        """加载mc.json配置文件"""
        if config_path is not None:
            self._config_path = config_path
        
        if self._config is not None:
            return self._config
            
        try:
            if not os.path.exists(self._config_path):
                logger.error("配置文件 %s 不存在", self._config_path)
                return None
                
            with open(self._config_path, "r", encoding="utf-8") as f:
                self._config = json.load(f)
            logger.info("成功加载配置文件: %s", self._config_path)
            return self._config
        except Exception as e:
            logger.error("加载mc.json配置失败: %s", str(e))
            return None
    
    def parse_config(self, config: Dict) -> Tuple[List[Dict], List[Dict]]:
        """解析mc.json配置，提取输入输出定义"""
        if not config:
            return [], []
        
        input_fields = []
        output_fields = []
        
        # 解析输入字段
        if "inputs" in config:
            for field_name, field_config in config["inputs"].items():
                field_info = {
                    "field_name": field_name,
                    "type": field_config.get("type", "file"),
                    "data_type": field_config.get("data_type", "text"),  # 新增：支持data_type
                    "file_types": field_config.get("file_types", []),
                    "description": field_config.get("description", ""),
                    "required": field_config.get("required", True),
                    "default": field_config.get("default", None),
                }
                input_fields.append(field_info)
        
        # 解析输出字段
        if "outputs" in config:
            for field_name, field_config in config["outputs"].items():
                field_info = {
                    "field_name": field_name,
                    "type": field_config.get("type", "file"),
                    "data_type": field_config.get("data_type", "text"),  # 新增：支持data_type
                    "file_types": field_config.get("file_types", []),
                    "description": field_config.get("description", ""),
                    "required": field_config.get("required", True),
                    "auto_zip": field_config.get("auto_zip", False),
                    "max_zip_size": field_config.get("max_zip_size", 100),
                }
                output_fields.append(field_info)
        
        return input_fields, output_fields
    
    def get_model_info(self) -> Dict:
        """获取模型信息"""
        if not self._config:
            return {}
        return self._config.get("model_info", {})
    
    def find_example_file(self, field_name: str, example_path: str = "examples") -> Optional[str]:
        """根据字段名查找示例文件"""
        if not os.path.exists(example_path):
            return None
        
        possible_extensions = [
            ".tif", ".tiff", ".jpg", ".jpeg", ".png", ".txt", 
            ".json", ".xml", ".csv", ".dat", ".inp", ".zip"
        ]
        
        # 完全匹配和小写匹配
        for ext in possible_extensions:
            exact_match = os.path.join(example_path, f"{field_name}{ext}")
            if os.path.exists(exact_match):
                return exact_match
                
            exact_match_lower = os.path.join(example_path, f"{field_name.lower()}{ext}")
            if os.path.exists(exact_match_lower):
                return exact_match_lower
        
        # 查找包含字段名的文件
        try:
            for filename in os.listdir(example_path):
                if field_name.lower() in filename.lower():
                    return os.path.join(example_path, filename)
        except (OSError, IOError) as e:
            logger.warning("无法读取示例数据目录 %s: %s", example_path, str(e))
        
        # 查找默认示例文件
        default_files = ["sample", "example", "demo", "test", "input", "data"]
        for default_name in default_files:
            for ext in possible_extensions:
                default_path = os.path.join(example_path, f"{default_name}{ext}")
                if os.path.exists(default_path):
                    return default_path
        
        return None