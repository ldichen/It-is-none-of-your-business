"""
文件和文件夹处理模块
Author: DiChen
Date: 2025-07-30
"""

import os
import shutil
import zipfile
from typing import List, Optional, Dict
from ..utils.logger import get_logger

# 初始化日志
logger = get_logger(__name__)


class FileHandler:
    """文件和文件夹处理器"""
    
    def cleanup_directory(self, directory: str) -> None:
        """清理目录"""
        try:
            if os.path.exists(directory):
                shutil.rmtree(directory)
                logger.debug("清理完成: %s", directory)
        except Exception as e:
            logger.error("清理失败: %s, 错误: %s", directory, str(e))
    
    def find_output_folder(self, output_dir: str, field_name: str) -> Optional[str]:
        """在输出目录中查找匹配的文件夹"""
        if not os.path.exists(output_dir):
            return None
        
        # 递归查找匹配的文件夹
        for root, dirs, _ in os.walk(output_dir):
            for dir_name in dirs:
                if dir_name == field_name:
                    return os.path.join(root, dir_name)
        
        return None
    
    def get_folder_size(self, folder_path: str) -> int:
        """计算文件夹大小（字节）"""
        total_size = 0
        try:
            for root, _, files in os.walk(folder_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    if os.path.exists(file_path):
                        total_size += os.path.getsize(file_path)
        except Exception as e:
            logger.error("计算文件夹大小失败: %s", str(e))
        return total_size


class ZipHandler:
    """压缩文件处理器"""
    
    def create_zip_from_folder(self, folder_path: str, field_name: str, 
                              max_size_mb: int = 100) -> Optional[str]:
        """将文件夹打包成zip文件"""
        try:
            file_handler = FileHandler()
            folder_size = file_handler.get_folder_size(folder_path)
            max_size_bytes = max_size_mb * 1024 * 1024
            
            if folder_size > max_size_bytes:
                print(f"文件夹 {field_name} 大小 {folder_size/1024/1024:.1f}MB 超过限制 {max_size_mb}MB，不进行打包")
                return None
            
            # 创建zip文件
            zip_path = os.path.join(os.path.dirname(folder_path), f"{field_name}.zip")
            
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for root, _, files in os.walk(folder_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        # 计算相对路径，保持文件夹结构
                        arcname = os.path.relpath(file_path, folder_path)
                        zipf.write(file_path, arcname)
            
            logger.info("文件夹打包成功: %s -> %s (%.1fMB)", folder_path, zip_path, folder_size/1024/1024)
            return zip_path
            
        except Exception as e:
            logger.error("文件夹打包失败: %s", str(e))
            return None


class FolderBrowserGenerator:
    """文件夹浏览器HTML生成器"""
    
    def generate_html(self, folder_path: str, field_name: str) -> str:
        """生成文件夹浏览器HTML"""
        try:
            html_parts = [
                f"<div style='border: 1px solid #ddd; padding: 15px; border-radius: 8px; background: #f9f9f9;'>",
                f"<h4>📁 {field_name}</h4>",
                f"<p><strong>路径:</strong> <code>{folder_path}</code></p>",
                "<details><summary><strong>📂 文件列表</strong></summary>",
                "<ul style='font-family: monospace; margin: 10px 0;'>",
            ]
            
            # 遍历文件夹生成文件列表
            file_count = 0
            for root, dirs, files in os.walk(folder_path):
                # 显示子文件夹
                for dir_name in dirs:
                    rel_path = os.path.relpath(os.path.join(root, dir_name), folder_path)
                    html_parts.append(f"<li>📁 {rel_path}/</li>")
                
                # 显示文件
                for file_name in files:
                    file_path = os.path.join(root, file_name)
                    rel_path = os.path.relpath(file_path, folder_path)
                    file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
                    
                    # 格式化文件大小
                    size_str = self._format_file_size(file_size)
                    
                    html_parts.append(
                        f"<li>📄 {rel_path} <span style='color: #666;'>({size_str})</span></li>"
                    )
                    file_count += 1
                    
                    # 限制显示文件数量，避免页面过长
                    if file_count > 50:
                        html_parts.append("<li>... 还有更多文件 ...</li>")
                        break
            
            html_parts.extend(["</ul>", "</details>", "</div>"])
            return "".join(html_parts)
            
        except Exception as e:
            logger.error("生成文件夹浏览器失败: %s", str(e))
            return f"<div style='color: red;'>生成文件夹浏览器失败: {e}</div>"
    
    def _format_file_size(self, file_size: int) -> str:
        """格式化文件大小"""
        if file_size < 1024:
            return f"{file_size}B"
        elif file_size < 1024 * 1024:
            return f"{file_size/1024:.1f}KB"
        else:
            return f"{file_size/(1024*1024):.1f}MB"


class OutputCollector:
    """输出文件收集器"""
    
    def __init__(self):
        self.file_handler = FileHandler()
        self.zip_handler = ZipHandler()
        self.browser_generator = FolderBrowserGenerator()
    
    def collect_outputs(self, output_dir: str, outputs_config: Dict) -> List[Optional[str]]:
        """基于mc.json配置收集模型输出（支持参数和文件）"""
        if not os.path.exists(output_dir):
            print(f"警告: 模型输出目录不存在: {output_dir}")
            return []
        
        output_files = []
        
        # 按mc.json中outputs的顺序查找文件、文件夹或参数
        for field_name, field_config in outputs_config.items():
            field_type = field_config.get("type", "file")
            file_types = field_config.get("file_types", [])
            found_item = None
            
            if field_type == "param":
                # 参数类型：从对应的txt文件读取参数值
                found_item = self._handle_param_output(
                    output_dir, field_name, field_config
                )
            elif field_type == "folder":
                found_item = self._handle_folder_output(
                    output_dir, field_name, field_config
                )
            else:
                found_item = self._handle_file_output(
                    output_dir, field_name, file_types
                )
            
            if found_item is not None:
                output_files.append(found_item)
            else:
                self._handle_missing_output(field_name, field_config, field_type)
                output_files.append(None)
        
        print(f"收集完成，共 {len([f for f in output_files if f is not None])} 个有效输出")
        return output_files
    
    def _handle_folder_output(self, output_dir: str, field_name: str, 
                             field_config: Dict) -> Optional[str]:
        """处理文件夹类型输出"""
        folder_path = self.file_handler.find_output_folder(output_dir, field_name)
        if not folder_path:
            return None
        
        auto_zip = field_config.get("auto_zip", False)
        max_size_mb = field_config.get("max_zip_size", 100)
        
        if auto_zip:
            # 尝试打包成zip
            zip_path = self.zip_handler.create_zip_from_folder(
                folder_path, field_name, max_size_mb
            )
            if zip_path:
                print(f"找到输出文件夹并打包: {field_name} -> {zip_path}")
                return zip_path
            else:
                # 打包失败，使用浏览器模式
                print(f"找到输出文件夹（浏览模式）: {field_name} -> {folder_path}")
                return f"FOLDER_BROWSER:{folder_path}"
        else:
            # 不打包，使用浏览器模式
            print(f"找到输出文件夹（浏览模式）: {field_name} -> {folder_path}")
            return f"FOLDER_BROWSER:{folder_path}"
    
    def _handle_file_output(self, output_dir: str, field_name: str, 
                           file_types: List[str]) -> Optional[str]:
        """处理文件类型输出"""
        for root, _, files in os.walk(output_dir):
            for file in files:
                file_path = os.path.join(root, file)
                file_name_no_ext, file_ext = os.path.splitext(file)
                
                # 检查文件名是否匹配字段名
                if file_name_no_ext == field_name:
                    # 如果指定了文件类型，检查扩展名
                    if file_types:
                        if file_ext.lower() in [ft.lower() for ft in file_types]:
                            print(f"找到输出文件: {field_name} -> {file_path}")
                            return file_path
                    else:
                        # 没有指定文件类型限制，直接匹配
                        print(f"找到输出文件: {field_name} -> {file_path}")
                        return file_path
        return None
    
    def _handle_param_output(self, output_dir: str, field_name: str, field_config: Dict) -> Optional[str]:
        """处理参数类型输出"""
        # 查找 {field_name}.txt 文件
        param_file = os.path.join(output_dir, f"{field_name}.txt")
        
        if os.path.exists(param_file):
            try:
                with open(param_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                
                if not content:
                    print(f"警告: 参数文件 {param_file} 为空")
                    return None
                
                # 根据data_type转换类型
                data_type = field_config.get("data_type", "text")
                if data_type == "number":
                    try:
                        # 尝试转换为数字
                        value = float(content)
                        print(f"找到参数输出: {field_name} = {value} (number)")
                        return value
                    except ValueError:
                        print(f"警告: 参数 {field_name} 无法转换为数字: {content}")
                        return None
                else:
                    # 文本类型
                    print(f"找到参数输出: {field_name} = '{content}' (text)")
                    return content
                    
            except Exception as e:
                print(f"读取参数文件失败: {param_file}, 错误: {e}")
                return None
        else:
            return None
    
    def _handle_missing_output(self, field_name: str, field_config: Dict, field_type: str):
        """处理未找到的输出"""
        output_type_name = {
            "param": "参数",
            "folder": "文件夹", 
            "file": "文件"
        }.get(field_type, "输出")
        
        if field_config.get("required", True):
            print(f"警告: 未找到必填{output_type_name}: {field_name}")
        else:
            print(f"可选{output_type_name}未找到: {field_name} (根据输入参数，此项可能不会生成)")