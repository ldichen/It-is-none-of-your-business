"""
Docker镜像构建器
"""

import sys
import json
import uuid
from pathlib import Path
from typing import Optional, Dict, Any
from ..utils.logger import get_logger
from .config import DockerConfig

try:
    import docker
except ImportError:
    raise ImportError("Docker库未安装，请运行: pip install docker>=7.0.0")

logger = get_logger(__name__)


class DockerBuilder:
    """Docker镜像构建器"""

    def __init__(self):
        try:
            self.client = docker.from_env()
            # 测试Docker连接
            self.client.ping()
            # 初始化配置
            self.config = DockerConfig()
        except docker.errors.DockerException as e:
            if "Cannot connect to the Docker daemon" in str(e):
                raise Exception("无法连接到Docker服务，请确保Docker已启动")
            else:
                raise Exception(f"Docker连接异常: {e}")
        except Exception as e:
            raise Exception(f"无法连接到Docker服务: {e}")

    def generate_image_name(self, model_name: str) -> str:
        """生成镜像名称: model_name + UUID"""
        clean_name = model_name.lower().replace(" ", "-").replace("_", "-")
        image_uuid = uuid.uuid4().hex[:8]
        return f"{clean_name}-{image_uuid}"

    def get_python_version(self) -> str:
        """获取当前Python版本对应的Docker基础镜像"""
        major, minor = sys.version_info.major, sys.version_info.minor

        # 版本映射策略
        version_map = {
            (3, 8): "python:3.8-slim",
            (3, 9): "python:3.9-slim",
            (3, 10): "python:3.10-slim",
            (3, 11): "python:3.11-slim",
            (3, 12): "python:3.12-slim",  # 3.12使用3.11兼容
        }

        return version_map.get((major, minor), "python:3.11-slim")

    def check_nested_directories(self, directory: Path, dir_name: str) -> bool:
        """检查目录是否存在多余的嵌套结构

        Args:
            directory: 要检查的目录路径
            dir_name: 目录名称 (如 'model' 或 'examples')

        Returns:
            bool: True表示结构正确，False表示存在嵌套问题
        """
        if not directory.exists() or not directory.is_dir():
            return True  # 目录不存在或不是目录，跳过检查

        # 获取目录下的所有内容
        contents = list(directory.iterdir())

        # 如果目录为空，这是正常的
        if not contents:
            return True

        # 检查是否只有一个子目录，且名称与父目录相同
        if len(contents) == 1 and contents[0].is_dir() and contents[0].name == dir_name:
            logger.warning(f"检测到多余的嵌套目录: {directory}/{dir_name}/")
            logger.warning(
                f"建议将 {directory}/{dir_name}/ 目录下的内容直接放在 {directory}/ 下"
            )
            return False

        return True

    def get_template_path(self, use_gpu: bool = False) -> Path:
        """获取模板文件路径
        
        Args:
            use_gpu: 是否使用GPU模板
        
        优先级：
        1. 项目级模板 (.inoyb/)
        2. 内置模板
        """
        # 确定模板文件名
        if use_gpu:
            template_name = "dockerfile-gpu.template"
            project_template_name = "dockerfile-gpu.template"
            template_desc = " (GPU版本，包含GDAL支持)"
        else:
            template_name = "dockerfile.template"
            project_template_name = "dockerfile.template"
            template_desc = " (CPU版本，包含GDAL支持)"
        
        # 1. 优先使用项目级模板
        project_template = Path(".inoyb") / project_template_name
        if project_template.exists():
            logger.info(f"使用项目级模板: {project_template}")
            return project_template
        
        # 2. 使用内置模板
        package_dir = Path(__file__).parent
        default_template = package_dir / "templates" / template_name
        
        if not default_template.exists():
            raise FileNotFoundError(f"未找到Dockerfile模板: {default_template}")
        
        logger.info(f"使用内置模板{template_desc}: {template_name}")
        return default_template

    def generate_dockerfile(
        self, project_path: Path, has_examples: bool = False, use_gpu: bool = False
    ) -> str:
        """从模板生成Dockerfile内容"""
        base_image = self.get_python_version()
        examples_copy = "COPY examples/ ./examples/" if has_examples else ""
        
        # 读取模板文件
        template_path = self.get_template_path(use_gpu=use_gpu)
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                template_content = f.read()
        except Exception as e:
            raise Exception(f"读取Dockerfile模板失败: {e}")
        
        # 替换模板变量
        try:
            dockerfile_content = template_content.format(
                base_image=base_image,
                examples_copy=examples_copy
            )
        except KeyError as e:
            raise Exception(f"Dockerfile模板变量错误: {e}")
        
        return dockerfile_content

    def validate_project(self, project_path: str) -> tuple[Dict[str, Any], bool]:
        """验证项目结构并读取配置

        Returns:
            tuple: (mc_config, has_examples)
        """
        project_path = Path(project_path)

        logger.info(f"验证项目结构: {project_path}")

        # 1. 检查必需文件
        required_files = ["gogogo.py", "mc.json", "requirements.txt"]
        missing_files = []

        for file in required_files:
            file_path = project_path / file
            if not file_path.exists():
                missing_files.append(file)
            elif not file_path.is_file():
                missing_files.append(f"{file} (不是文件)")

        if missing_files:
            raise FileNotFoundError(
                f"❌ 项目结构不正确，缺少必需文件: {', '.join(missing_files)}"
            )

        # 2. 检查model目录
        model_dir = project_path / "model"
        if not model_dir.exists():
            raise FileNotFoundError("❌ 项目结构不正确，缺少model目录")

        if not model_dir.is_dir():
            raise FileNotFoundError("❌ model不是目录")

        # 检查model目录是否为空
        model_contents = list(model_dir.iterdir())
        if not model_contents:
            logger.warning("⚠️  model目录为空")

        # 3. 检查model目录嵌套结构
        if not self.check_nested_directories(model_dir, "model"):
            raise ValueError("❌ model目录存在多余的嵌套结构，请修正后重试")

        # 4. 检查examples目录（可选）
        examples_dir = project_path / "examples"
        has_examples = False

        if examples_dir.exists():
            if not examples_dir.is_dir():
                logger.warning("⚠️  examples存在但不是目录，将被忽略")
            else:
                has_examples = True
                logger.info("✅ 检测到examples目录，将包含在镜像中")

                # 检查examples目录嵌套结构
                if not self.check_nested_directories(examples_dir, "examples"):
                    raise ValueError("❌ examples目录存在多余的嵌套结构，请修正后重试")

        # 5. 读取mc.json配置
        mc_json_path = project_path / "mc.json"
        try:
            with open(mc_json_path, "r", encoding="utf-8") as f:
                mc_config = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"❌ mc.json格式错误: {e}")
        except Exception as e:
            raise ValueError(f"❌ 无法读取mc.json: {e}")

        # 6. 验证mc.json结构
        if not isinstance(mc_config, dict):
            raise ValueError("❌ mc.json根元素必须是对象")

        if "model_info" not in mc_config:
            raise ValueError("❌ mc.json中缺少model_info字段")

        model_info = mc_config["model_info"]
        if not isinstance(model_info, dict):
            raise ValueError("❌ mc.json中model_info必须是对象")

        if "name" not in model_info:
            raise ValueError("❌ mc.json中缺少model_info.name字段")

        model_name = model_info["name"]
        if not isinstance(model_name, str) or not model_name.strip():
            raise ValueError("❌ mc.json中model_info.name必须是非空字符串")

        logger.info(f"✅ 项目结构验证通过")
        logger.info(f"   模型名称: {model_name}")
        logger.info(f"   包含examples: {'是' if has_examples else '否'}")

        return mc_config, has_examples

    def build_image(self, project_path: str = ".", use_gpu: bool = False) -> tuple[str, str]:
        """构建Docker镜像

        Args:
            project_path: 项目路径
            use_gpu: 是否使用GPU支持

        Returns:
            tuple: (image_name, image_id)
        """
        project_path = Path(project_path).resolve()

        logger.info(f"🚀 开始构建Docker镜像")
        logger.info(f"   项目路径: {project_path}")

        # 验证项目结构
        try:
            mc_config, has_examples = self.validate_project(str(project_path))
            model_name = mc_config["model_info"]["name"]
        except (FileNotFoundError, ValueError) as e:
            logger.error(str(e))
            raise

        # 生成镜像名称
        image_name = self.generate_image_name(model_name)
        full_image_name = f"inoyb/{image_name}"

        logger.info(f"🏷️  镜像名称: {full_image_name}")

        # 生成Dockerfile
        dockerfile_content = self.generate_dockerfile(project_path, has_examples, use_gpu)
        dockerfile_path = project_path / "Dockerfile.inoyb"

        try:
            # 写入临时Dockerfile
            with open(dockerfile_path, "w", encoding="utf-8") as f:
                f.write(dockerfile_content)

            logger.info("🔨 开始构建镜像...")

            # 构建镜像
            image, logs = self.client.images.build(
                path=str(project_path),
                dockerfile="Dockerfile.inoyb",
                tag=full_image_name,
                rm=True,  # 删除中间容器
                pull=True,  # 拉取最新基础镜像
            )

            # 输出构建日志
            for log in logs:
                if "stream" in log:
                    stream_content = log["stream"].strip()
                    if stream_content:  # 只输出非空内容
                        logger.info(f"   {stream_content}")

            logger.info(f"✅ 镜像构建成功: {full_image_name}")
            return full_image_name, image.id

        finally:
            # 清理临时Dockerfile
            if dockerfile_path.exists():
                dockerfile_path.unlink()
                logger.info("🧹 已清理临时Dockerfile")

    def list_local_images(self, project_filter: Optional[str] = None) -> list:
        """列出本地inoyb镜像"""
        try:
            images = self.client.images.list()
            inoyb_images = []

            for image in images:
                for tag in image.tags:
                    if tag.startswith("inoyb/"):
                        image_info = {
                            "name": tag,
                            "id": image.id[:12],
                            "created": image.attrs["Created"],
                            "size": image.attrs["Size"],
                        }

                        if project_filter is None or project_filter in tag:
                            inoyb_images.append(image_info)

            return sorted(inoyb_images, key=lambda x: x["created"], reverse=True)

        except Exception as e:
            logger.error(f"获取镜像列表失败: {e}")
            return []

    def remove_image(self, image_name: str) -> bool:
        """删除指定镜像"""
        try:
            self.client.images.remove(image_name, force=True)
            logger.info(f"镜像删除成功: {image_name}")
            return True
        except Exception as e:
            logger.error(f"删除镜像失败 {image_name}: {e}")
            return False

    def cleanup_old_images(self, keep_count: int = 3) -> int:
        """清理旧镜像，保留最新的几个"""
        images = self.list_local_images()

        if len(images) <= keep_count:
            return 0

        # 按项目分组
        project_groups = {}
        for img in images:
            # 提取项目名 (去掉UUID部分)
            name_parts = img["name"].replace("inoyb/", "").split("-")
            if len(name_parts) > 1:
                project_name = "-".join(name_parts[:-1])  # 去掉最后的UUID
                if project_name not in project_groups:
                    project_groups[project_name] = []
                project_groups[project_name].append(img)

        removed_count = 0
        for project_name, project_images in project_groups.items():
            if len(project_images) > keep_count:
                # 保留最新的keep_count个，删除其余的
                to_remove = project_images[keep_count:]
                for img in to_remove:
                    if self.remove_image(img["name"]):
                        removed_count += 1

        return removed_count
