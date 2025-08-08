"""
Gradio UI组件管理模块
Author: DiChen
Date: 2025-07-30
"""

import gradio as gr
from typing import Dict, List, Tuple, Any


class UIComponentFactory:
    """Gradio组件工厂类"""
    
    def get_component_from_type(self, field_config: Dict) -> Tuple[Any, Dict]:
        """根据mc.json中的type配置返回对应的Gradio组件"""
        field_type = field_config.get("type", "file")
        file_types = field_config.get("file_types", [])
        
        # 参数类型处理
        if field_type == "param":
            data_type = field_config.get("data_type", "text")
            if data_type == "number":
                return gr.Number, {"value": field_config.get("default", 0)}
            else:  # text 或其他类型都当作文本处理
                return gr.Textbox, {
                    "lines": 3, 
                    "max_lines": 10,
                    "value": field_config.get("default", "")
                }
        
        # 特殊处理：如果是geodata类型的geojson文件，使用JSON组件
        if field_type == "geodata" and field_config.get("file_extension") in [".geojson", ".json"]:
            return gr.JSON, {"value": {}}
        
        # 文件类型组件
        if field_type == "file":
            component_config = {"type": "filepath"}
            if file_types:
                component_config["file_types"] = file_types
            return gr.File, component_config
        
        # 图片类型
        elif field_type == "image":
            return gr.Image, {"type": "filepath"}
        
        # 视频类型
        elif field_type == "video":
            return gr.Video, {"type": "filepath"}
        
        # 音频类型
        elif field_type == "audio":
            return gr.Audio, {"type": "filepath"}
        
        # 文本类型
        elif field_type == "text":
            return gr.Textbox, {"lines": 3, "max_lines": 10}
        
        # 数字类型
        elif field_type == "number":
            return gr.Number, {"value": field_config.get("default", 0)}
        
        # JSON类型
        elif field_type == "json":
            return gr.JSON, {"value": field_config.get("default", {})}
        
        # 文件夹类型
        elif field_type == "folder":
            return gr.File, {"type": "filepath", "file_count": "directory"}
        
        # 压缩包类型
        elif field_type == "zip":
            return gr.File, {
                "type": "filepath",
                "file_types": [".zip", ".tar", ".gz", ".rar"],
            }
        
        # 地理数据类型
        elif field_type == "geodata":
            return gr.File, {
                "type": "filepath",
                "file_types": [".tif", ".tiff", ".nc", ".hdf", ".h5", ".shp", ".geojson", ".kml", ".json"],
            }
        
        # 默认文件类型
        else:
            component_config = {"type": "filepath"}
            if file_types:
                component_config["file_types"] = file_types
            return gr.File, component_config
    
    def create_input_component(self, field_info: Dict) -> Any:
        """创建单个输入组件"""
        component_class, component_config = self.get_component_from_type(field_info)
        
        # 判断是否必填
        required_text = "（必填）" if field_info["required"] else "（选填）"
        
        # 创建组件标签：只显示字段名称
        component_config["label"] = field_info['field_name']
        
        # 设置默认值
        if "default" in field_info and field_info["default"] is not None:
            if component_class == gr.Textbox:
                component_config["value"] = field_info["default"]
            elif component_class == gr.Number:
                component_config["value"] = field_info["default"]
            elif component_class == gr.JSON:
                component_config["value"] = field_info["default"]
        
        return component_class(**component_config)
    
    def create_output_component(self, field_info: Dict) -> Any:
        """创建单个输出组件"""
        field_type = field_info.get("type", "file")
        
        # 对于 param 类型，需要特殊处理
        if field_type == "param":
            data_type = field_info.get("data_type", "text")
            label = f"{field_info['field_name']} - {field_info['description']}"
            
            if data_type == "number":
                return gr.Number(
                    label=label,
                    interactive=False,
                    precision=4,
                    value=0
                )
            else:  # text
                return gr.Textbox(
                    label=label,
                    interactive=False,
                    lines=3,
                    value=""
                )
        
        # 对于 folder 类型，需要特殊处理
        elif field_type == "folder":
            auto_zip = field_info.get("auto_zip", False)
            if auto_zip:
                # 如果自动打包，使用文件组件
                return gr.File(
                    label=f"📦 {field_info['field_name']} - {field_info['description']} (已打包)",
                    interactive=False,
                )
            else:
                # 如果不打包，使用HTML组件显示文件夹浏览器
                return gr.HTML(
                    label=f"📁 {field_info['field_name']} - {field_info['description']}",
                    value="",
                )
        else:
            # 其他类型的正常处理
            component_class, component_config = self.get_component_from_type(field_info)
            
            # 输出组件配置
            component_config["label"] = (
                f"{field_info['field_name']} - {field_info['description']}"
            )
            
            # 对于输出组件，移除 type="filepath" 配置，直接用于文件下载
            if "type" in component_config and component_config["type"] == "filepath":
                del component_config["type"]
            
            # 对于文件类型的输出组件，禁止上传，只允许下载
            if component_class == gr.File:
                # File组件设置为只读，禁止上传
                component_config["interactive"] = False
                component_config["show_label"] = True
            else:
                # 其他类型设为只读
                component_config["interactive"] = False
            
            # 对于某些组件类型，需要特殊处理
            if component_class == gr.Textbox:
                component_config["value"] = ""
            elif component_class == gr.JSON:
                component_config["value"] = {}
            elif component_class == gr.Number:
                component_config["value"] = 0
            
            return component_class(**component_config)
    
    def create_preview_component(self, field_info: Dict) -> gr.Image:
        """创建预览组件"""
        return gr.Image(
            label=f"🔍 {field_info['field_name']} - 预览",
            visible=False,
            interactive=False,
            show_label=True,
            show_download_button=False
        )
    
    def get_layout_type(self, input_count: int, output_count: int) -> str:
        """根据输入输出数量确定布局类型"""
        if input_count <= 2 and output_count <= 2:
            return "simple"
        elif input_count <= 4 and output_count <= 4:
            return "medium"
        else:
            return "complex"


class UILayoutManager:
    """UI布局管理器"""
    
    def __init__(self, component_factory: UIComponentFactory):
        self.component_factory = component_factory

    def create_model_info_section(self, model_info: Dict) -> gr.Markdown:
        """创建模型信息展示区域"""
        if not model_info:
            return gr.Markdown(
                "<div style='text-align: center;'>### ⚠️ 无法加载模型信息</div>"
            )
        
        model_name = model_info.get("name", "未知模型")
        model_description = model_info.get("description", "暂无描述")
        model_version = model_info.get("version", "1.0.0")
        
        status_text = "### 🟢 Status: Model ready!"
        
        info_text = f"""
        <div style='text-align: center;'>
        
        ## {model_name} v{model_version}
        {model_description}
        
        {status_text}
        
        </div>
        """
        
        return gr.Markdown(info_text)
    
    def create_layout(self, input_fields: List[Dict], output_fields: List[Dict], 
                     layout_type: str) -> Tuple[List[Any], List[Any], List[Any]]:
        """根据布局类型创建界面组件"""
        input_components = []
        output_components = []
        preview_components = []
        
        if layout_type == "simple":
            # 简单布局：左右分栏
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### 📥 输入数据")
                    for field_info in input_fields:
                        comp = self.component_factory.create_input_component(field_info)
                        input_components.append(comp)
                
                with gr.Column(scale=1):
                    gr.Markdown("### 📤 输出结果")
                    for field_info in output_fields:
                        comp = self.component_factory.create_output_component(field_info)
                        output_components.append(comp)
                        
                        # 预览组件（仅geodata类型）
                        if field_info.get("type") == "geodata":
                            preview_comp = self.component_factory.create_preview_component(field_info)
                            preview_components.append(preview_comp)
                        else:
                            # 其他类型添加占位的不可见预览组件
                            placeholder_preview = gr.Image(visible=False)
                            preview_components.append(placeholder_preview)
        
        elif layout_type == "medium":
            # 中等布局：分组显示
            gr.Markdown("### 📥 输入数据")
            input_groups = [input_fields[i:i+2] for i in range(0, len(input_fields), 2)]
            for group in input_groups:
                with gr.Row():
                    for field_info in group:
                        comp = self.component_factory.create_input_component(field_info)
                        input_components.append(comp)
            
            gr.Markdown("### 📤 输出结果")
            output_groups = [output_fields[i:i+2] for i in range(0, len(output_fields), 2)]
            for group in output_groups:
                with gr.Row():
                    for field_info in group:
                        comp = self.component_factory.create_output_component(field_info)
                        output_components.append(comp)
                        
                        # 预览组件（仅geodata类型）
                        if field_info.get("type") == "geodata":
                            preview_comp = self.component_factory.create_preview_component(field_info)
                            preview_components.append(preview_comp)
                        else:
                            # 其他类型添加占位的不可见预览组件
                            placeholder_preview = gr.Image(visible=False)
                            preview_components.append(placeholder_preview)
        
        else:
            # 复杂布局：多行多列
            gr.Markdown("### 📥 输入数据")
            input_groups = [input_fields[i:i+3] for i in range(0, len(input_fields), 3)]
            for group in input_groups:
                with gr.Row():
                    for field_info in group:
                        comp = self.component_factory.create_input_component(field_info)
                        input_components.append(comp)
            
            gr.Markdown("### 📤 输出结果")
            output_groups = [output_fields[i:i+3] for i in range(0, len(output_fields), 3)]
            for group in output_groups:
                with gr.Row():
                    for field_info in group:
                        comp = self.component_factory.create_output_component(field_info)
                        output_components.append(comp)
                        
                        # 预览组件（仅geodata类型）
                        if field_info.get("type") == "geodata":
                            preview_comp = self.component_factory.create_preview_component(field_info)
                            preview_components.append(preview_comp)
                        else:
                            # 其他类型添加占位的不可见预览组件
                            placeholder_preview = gr.Image(visible=False)
                            preview_components.append(placeholder_preview)
        
        return input_components, output_components, preview_components