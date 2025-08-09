"""
Docker镜像构建器
"""

import sys
import json
import uuid
import time
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
        """生成镜像名称: model_name:UUID"""
        clean_name = model_name.lower().replace(" ", "-").replace("_", "-")
        image_uuid = uuid.uuid4().hex[:8]
        return f"{clean_name}:{image_uuid}"

    def get_miniconda3_version(self) -> str:
        """获取当前miniconda3版本对应的Docker基础镜像"""
        major, minor = sys.version_info.major, sys.version_info.minor

        # 版本映射策略 - 使用miniconda3以支持rasterio和GDAL
        version_map = {
            (3, 8): "continuumio/miniconda3:4.9.2",
            (3, 9): "continuumio/miniconda3:4.12.0",
            (3, 10): "continuumio/miniconda3:22.11.1",
            (3, 11): "continuumio/miniconda3:23.3.1-0",
            (3, 12): "continuumio/miniconda3:24.3.0-0",
            (3, 13): "continuumio/miniconda3:25.3.1-1",
        }

        return version_map.get((major, minor), "continuumio/miniconda3:23.3.1-0")

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
            template_desc = " (GPU版本，包含rasterio/GDAL支持)"
        else:
            template_name = "dockerfile.template"
            project_template_name = "dockerfile.template"
            template_desc = " (CPU版本，包含rasterio/GDAL支持)"

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
        self,
        project_path: Path,
        has_examples: bool = False,
        use_gpu: bool = False,
        registry: str = None,
        base_image_override: str = None,
    ) -> str:
        """从模板生成Dockerfile内容"""
        # 获取基础镜像名
        original_base_image = self.get_miniconda3_version()

        # 解析最终的基础镜像地址（包含项目配置）
        resolved_base_image = self.config.resolve_base_image_with_project(
            image=original_base_image,
            project_path=str(project_path),
            cli_registry=registry,
            cli_base_image=base_image_override,
        )

        examples_copy = (
            "COPY --chown=$APP_USER:$APP_USER examples/ ./examples/"
            if has_examples
            else ""
        )

        # 日志输出
        if resolved_base_image != original_base_image:
            logger.info(f"📦 基础镜像: {original_base_image} -> {resolved_base_image}")
        else:
            logger.info(f"📦 基础镜像: {resolved_base_image}")

        # 读取模板文件
        template_path = self.get_template_path(use_gpu=use_gpu)
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                template_content = f.read()
        except Exception as e:
            raise Exception(f"读取Dockerfile模板失败: {e}")

        # 替换模板变量
        try:
            dockerfile_content = template_content.format(
                base_image=resolved_base_image, examples_copy=examples_copy
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
        
        # 验证模型名称长度不超过27个字符
        if len(model_name) > 27:
            raise ValueError(f"❌ mc.json中model_info.name长度不能超过27个字符，当前长度：{len(model_name)}")
            

        logger.info(f"✅ 项目结构验证通过")
        logger.info(f"   模型名称: {model_name}")
        logger.info(f"   包含examples: {'是' if has_examples else '否'}")

        return mc_config, has_examples

    def build_image(
        self,
        project_path: str = ".",
        use_gpu: bool = False,
        registry: str = None,
        base_image: str = None,
    ) -> tuple[str, str]:
        """构建Docker镜像 - 带重试机制的包装器"""
        return self._build_image_with_retry(project_path, use_gpu, registry, base_image)

    def _build_image_with_retry(
        self,
        project_path: str = ".",
        use_gpu: bool = False,
        registry: str = None,
        base_image: str = None,
        max_retries: int = 3,
    ) -> tuple[str, str]:
        """带重试机制的镜像构建"""
        for attempt in range(max_retries):
            try:
                return self._build_image_internal(
                    project_path, use_gpu, registry, base_image
                )
            except Exception as e:
                error_msg = str(e)

                # 检查是否为网络相关错误
                if any(
                    keyword in error_msg.lower()
                    for keyword in [
                        "tls: bad record mac",
                        "manifest unknown",
                        "connection reset",
                        "timeout",
                        "network",
                        "registry-1.docker.io",
                        "auth.docker.io",
                    ]
                ):
                    if attempt < max_retries - 1:
                        wait_time = 2**attempt
                        logger.warning(
                            f"🔄 构建失败 (尝试 {attempt + 1}/{max_retries}): 网络错误"
                        )
                        logger.info(f"   等待 {wait_time} 秒后重试...")
                        time.sleep(wait_time)
                        continue
                    else:
                        # 最后一次重试失败，提供解决方案
                        self._handle_network_error(error_msg)
                        raise e
                else:
                    # 非网络错误，直接抛出
                    raise e

        # 不应该到达这里
        raise Exception("重试次数耗尽")

    def _handle_network_error(self, error_msg: str):
        """处理网络相关错误，提供解决方案"""
        print("\n" + "=" * 60)

        if "tls: bad record mac" in error_msg.lower():
            print("❌ TLS 连接错误 - 网络连接问题")
            print("\n💡 这通常是由以下原因造成的：")
            print("   • 网络连接不稳定或中断")
            print("   • 防火墙/代理干扰 TLS 连接")
            print("   • Docker Hub 访问受限（国内网络环境）")

        elif "manifest unknown" in error_msg.lower():
            print("❌ 镜像不存在或访问受限")
            print("\n💡 这通常是由以下原因造成的：")
            print("   • 镜像名称或版本不正确")
            print("   • Docker Hub 访问受限")
            print("   • 镜像仓库暂时不可用")

        else:
            print("❌ 网络相关错误")
            print(f"   错误详情: {error_msg}")

        print("\n🔧 建议解决方案：")
        print("   1. 配置镜像加速（国内用户强烈推荐）：")
        print(
            "      inoyb config set registry.mirror registry.cn-hangzhou.aliyuncs.com"
        )
        print()
        print("   2. 使用阿里云镜像源构建：")
        print("      inoyb build --registry registry.cn-hangzhou.aliyuncs.com/library")
        print()
        print("   3. 直接指定国内镜像：")
        print(
            "      inoyb build --base-image registry.cn-hangzhou.aliyuncs.com/library/continuumio/miniconda3:24.3.0-0"
        )
        print()
        print("   4. 检查网络连接：")
        print("      • 确保网络连接稳定")
        print("      • 如使用代理，设置: export HTTPS_PROXY=http://proxy:port")
        print("      • 重启 Docker 服务")
        print()
        print("   5. 稍后重试构建命令")
        print("=" * 60 + "\n")

    def _should_show_log(self, log_content: str) -> bool:
        """判断是否应该显示日志内容"""
        if not log_content or not log_content.strip():
            return False

        # 过滤掉的错误信息
        filtered_messages = [
            "logging driver does not support reading",
            "configured logging driver does not support reading",
            "Error response from daemon: configured logging driver",
        ]

        # 过滤掉的详细信息（减少冗余输出）
        verbose_messages = [
            "sha256:",
            "digest:",
            "status: pulling",
            "status: extracting",
            "status: verifying",
            "status: download complete",
            "status: downloading",
            "status: waiting",
            "already exists",
            "pull complete",
        ]

        log_lower = log_content.lower()

        # 过滤错误信息
        for filtered_msg in filtered_messages:
            if filtered_msg.lower() in log_lower:
                return False

        # 过滤冗长的下载详情（保留重要信息）
        for verbose_msg in verbose_messages:
            if verbose_msg in log_lower:
                return False

        return True

    def _format_log_with_color(self, log_content: str, log_type: str = "info") -> str:
        """为日志内容添加颜色格式"""
        # ANSI颜色代码
        colors = {
            "step": "\033[1;36m",  # 青色加粗 - 构建步骤
            "success": "\033[1;32m",  # 绿色加粗 - 成功信息
            "warning": "\033[1;33m",  # 黄色加粗 - 警告
            "error": "\033[1;31m",  # 红色加粗 - 错误
            "info": "\033[0;37m",  # 白色 - 普通信息
            "dim": "\033[0;90m",  # 暗色 - 次要信息
            "reset": "\033[0m",  # 重置
        }

        color = colors.get(log_type, colors["info"])
        return f"{color}{log_content}{colors['reset']}"

    def _get_log_type_and_content(self, log_content: str) -> tuple:
        """分析日志内容类型并返回格式化后的内容"""
        log_lower = log_content.lower()

        # Step 信息
        if log_content.startswith("Step "):
            return "step", f"🔄 {log_content}"

        # 成功信息
        if any(
            keyword in log_lower for keyword in ["successfully", "complete", "finished"]
        ):
            return "success", f"✅ {log_content}"

        # 警告信息
        if any(keyword in log_lower for keyword in ["warning", "warn", "deprecated"]):
            return "warning", f"⚠️  {log_content}"

        # 错误信息
        if any(keyword in log_lower for keyword in ["error", "failed", "fatal"]):
            return "error", f"❌ {log_content}"

        # 重要操作
        if any(
            keyword in log_lower
            for keyword in ["installing", "downloading", "copying", "building"]
        ):
            return "info", f"📦 {log_content}"

        # 其他信息显示为次要
        return "dim", f"   {log_content}"

    def _decode_log_content(self, content) -> str:
        """解码日志内容，处理字符串和字节"""
        if content is None:
            return ""

        if isinstance(content, bytes):
            try:
                return content.decode("utf-8").strip()
            except UnicodeDecodeError:
                return content.decode("utf-8", errors="ignore").strip()
        elif isinstance(content, str):
            return content.strip()
        else:
            return str(content).strip()

    def _build_image_internal(
        self,
        project_path: str = ".",
        use_gpu: bool = False,
        registry: str = None,
        base_image: str = None,
    ) -> tuple[str, str]:
        """构建Docker镜像

        Args:
            project_path: 项目路径
            use_gpu: 是否使用GPU支持
            registry: 镜像仓库前缀
            base_image: 完整的基础镜像名

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
        dockerfile_content = self.generate_dockerfile(
            project_path, has_examples, use_gpu, registry, base_image
        )
        dockerfile_path = project_path / "Dockerfile.inoyb"

        try:
            # 写入临时Dockerfile
            with open(dockerfile_path, "w", encoding="utf-8") as f:
                f.write(dockerfile_content)

            logger.info("🔨 开始构建镜像...")
            logger.info("💡💡💡💡💡💡💡💡💡💡💡💡💡💡💡💡💡💡💡💡💡💡💡💡💡")

            # 使用低级API进行流式构建
            build_args = {}  # 可以传递构建参数

            try:
                # 使用低级API构建，支持实时流式输出
                image_id = None
                step_count = 0

                # 使用低级API
                build_logs = self.client.api.build(
                    path=str(project_path),
                    dockerfile="Dockerfile.inoyb",
                    tag=full_image_name,
                    rm=True,  # 删除中间容器
                    pull=True,  # 拉取最新基础镜像
                    forcerm=True,  # 强制删除中间容器（即使构建失败）
                    buildargs=build_args,
                )

                for log_line in build_logs:
                    # 解析日志行（可能是字节格式）
                    if isinstance(log_line, bytes):
                        try:
                            import json

                            log_line = json.loads(log_line.decode("utf-8"))
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            continue

                    # 实时处理每一行日志
                    if isinstance(log_line, dict):
                        if "stream" in log_line:
                            stream_content = log_line["stream"].rstrip("\n\r")
                            if stream_content and self._should_show_log(stream_content):
                                # 获取日志类型和格式化内容
                                log_type, formatted_content = (
                                    self._get_log_type_and_content(stream_content)
                                )
                                colored_output = self._format_log_with_color(
                                    formatted_content, log_type
                                )

                                # 检测构建步骤
                                if stream_content.startswith("Step "):
                                    step_count += 1
                                    print(f"\n{colored_output}")
                                else:
                                    # 根据类型决定是否缩进
                                    if log_type in [
                                        "step",
                                        "success",
                                        "warning",
                                        "error",
                                    ]:
                                        print(colored_output)
                                    else:
                                        print(colored_output)
                                # 强制刷新输出缓冲区，确保实时显示
                                sys.stdout.flush()

                        elif "error" in log_line:
                            error_msg = log_line["error"].rstrip("\n\r")
                            if self._should_show_log(error_msg):
                                colored_error = self._format_log_with_color(
                                    f"❌ 构建错误: {error_msg}", "error"
                                )
                                print(colored_error)
                                raise Exception(f"构建失败: {error_msg}")

                        elif "errorDetail" in log_line:
                            error_detail = log_line["errorDetail"]
                            if "message" in error_detail:
                                error_msg = error_detail["message"]
                                if self._should_show_log(error_msg):
                                    colored_error = self._format_log_with_color(
                                        f"❌ 错误详情: {error_msg}", "error"
                                    )
                                    print(colored_error)
                                    raise Exception(f"构建失败: {error_msg}")

                        # 捕获最终的镜像ID
                        elif "aux" in log_line and "ID" in log_line["aux"]:
                            image_id = log_line["aux"]["ID"]

                    elif isinstance(log_line, (str, bytes)):
                        # 处理字符串或字节格式的日志
                        if isinstance(log_line, bytes):
                            try:
                                decoded_log = log_line.decode("utf-8").rstrip("\n\r")
                            except UnicodeDecodeError:
                                decoded_log = log_line.decode(
                                    "utf-8", errors="ignore"
                                ).rstrip("\n\r")
                        else:
                            decoded_log = log_line.rstrip("\n\r")

                        if self._should_show_log(decoded_log):
                            log_type, formatted_content = (
                                self._get_log_type_and_content(decoded_log)
                            )
                            colored_output = self._format_log_with_color(
                                formatted_content, log_type
                            )
                            print(colored_output)
                            sys.stdout.flush()

                # 获取构建成功的镜像对象
                if image_id:
                    image = self.client.images.get(image_id)
                else:
                    # 如果没有获取到image_id，尝试通过tag获取
                    image = self.client.images.get(full_image_name)

                # 保持原有的logger调用以维持兼容性，同时添加彩色输出
                logger.info(f"✅ 镜像构建成功: {full_image_name}")
                return full_image_name, image.id

            except Exception as build_error:
                # 处理构建错误
                error_msg = str(build_error)
                if "No such image" in error_msg or "404" in error_msg:
                    raise Exception(
                        f"构建失败: 中间镜像丢失，建议运行 'inoyb images prune' 清理缓存后重试"
                    )
                elif any(
                    keyword in error_msg.lower()
                    for keyword in [
                        "tls: bad record mac",
                        "manifest unknown",
                        "connection reset",
                        "timeout",
                        "network",
                        "registry-1.docker.io",
                        "auth.docker.io",
                    ]
                ):
                    # 网络相关错误，让外层重试机制处理
                    raise build_error
                else:
                    raise build_error

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
                        # 获取详细的镜像信息
                        image_info = {
                            "name": tag,
                            "id": image.id[:12],
                            "created": image.attrs["Created"],
                            "size": image.attrs["Size"],
                        }
                        # 计算模型文件大小
                        image_info["model_size"] = self._calculate_model_size(image)

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
            # 提取项目名 (去掉UUID标签部分)
            full_name = img["name"].replace("inoyb/", "")
            if ":" in full_name:
                project_name = full_name.split(":")[0]  # 去掉标签部分
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

    def _calculate_model_size(self, image) -> int:
        """通过分析镜像历史来计算模型文件大小"""
        try:
            # 获取镜像的构建历史
            history = image.history()

            model_size = 0
            found_layers = []

            for layer in history:
                created_by = layer.get("CreatedBy", "")
                created_by_lower = created_by.lower()
                layer_size = layer.get("Size", 0)

                # 跳过空层
                if layer_size == 0:
                    continue

                # 识别复制模型文件的层
                # 匹配各种可能的模型文件复制指令
                model_patterns = [
                    "copy model/",
                    "copy model .",
                    "copy ./model",
                    "copy model/ .",
                    "copy model/ ./model",
                    "add model/",
                    "add model .",
                    "copy --from=builder model/",
                    # 匹配我们的标准指令
                    "copy model/ ./model/",
                ]

                is_model_layer = False

                if any(pattern in created_by_lower for pattern in model_patterns):
                    model_size += layer_size
                    found_layers.append(f"精确匹配: {created_by}")
                    is_model_layer = True

                # 特殊处理：有时候模型文件和其他文件一起复制
                elif (
                    "copy" in created_by_lower
                    and (
                        "model" in created_by_lower
                        or any(
                            ext in created_by_lower
                            for ext in [
                                "*.pkl",
                                "*.pth",
                                "*.safetensors",
                                "*.onnx",
                                "*.bin",
                            ]
                        )
                        or any(
                            keyword in created_by_lower
                            for keyword in ["checkpoint", "weights"]
                        )
                    )
                    and layer_size > 10 * 1024 * 1024
                ):  # 大于10MB的层
                    model_size += layer_size
                    found_layers.append(f"可能匹配: {created_by}")
                    is_model_layer = True

                if is_model_layer:
                    logger.debug(
                        f"找到模型层 ({self._format_size(layer_size)}): {created_by}"
                    )

            # 如果找到了模型层，记录摘要信息
            if model_size > 0:
                logger.debug(
                    f"模型大小计算完成: {self._format_size(model_size)} (来自 {len(found_layers)} 层)"
                )

            return model_size

        except Exception as e:
            logger.debug(f"无法分析模型大小: {e}")
            return 0

    def _format_size(self, size_bytes: int) -> str:
        """格式化字节大小为可读格式"""
        if size_bytes > 1024 * 1024 * 1024:  # GiB
            return f"{size_bytes / (1024**3):.2f} GiB"
        elif size_bytes > 1024 * 1024:  # MiB
            return f"{size_bytes / (1024**2):.2f} MiB"
        elif size_bytes > 1024:  # KiB
            return f"{size_bytes / 1024:.2f} KiB"
        else:
            return f"{size_bytes} B"

    def cleanup_build_cache(self) -> bool:
        """清理 Docker 构建缓存，可能解决日志驱动问题"""
        try:
            # 清理构建缓存
            self.client.api.prune_builds()
            logger.info("✅ Docker 构建缓存已清理")

            # 清理无用的容器
            self.client.containers.prune()
            logger.info("✅ 无用容器已清理")

            return True
        except Exception as e:
            logger.error(f"清理缓存失败: {e}")
            return False

    def export_image(
        self, image_name: str, output_path: str = None, export_dir: str = None
    ) -> bool:
        """将镜像导出为tar包

        Args:
            image_name: 镜像名称 (如: inoyb/model-name:tag)
            output_path: 输出文件路径 (如: model.tar)，为空时自动生成
            export_dir: 导出目录路径，默认为当前目录

        Returns:
            bool: 导出是否成功
        """
        try:
            # 验证镜像是否存在
            try:
                self.client.images.get(image_name)
            except Exception:
                logger.error(f"镜像不存在: {image_name}")
                return False

            # 设置导出目录，默认为当前目录
            if export_dir:
                export_directory = Path(export_dir)
                # 确保导出目录存在
                export_directory.mkdir(parents=True, exist_ok=True)
            else:
                export_directory = Path(".")  # 当前目录

            # 生成输出文件名
            if not output_path:
                # 从镜像名生成文件名: inoyb/model-name:tag -> model-name_tag.tar
                clean_name = (
                    image_name.replace("inoyb/", "").replace(":", "-").replace("/", "_")
                )
                filename = f"{clean_name}.tar"
            else:
                filename = output_path
                # 确保输出路径有.tar扩展名
                if not filename.endswith(".tar"):
                    filename += ".tar"

            # 组合完整路径
            output_file = export_directory / filename

            logger.info(f"📦 开始导出镜像: {image_name}")
            logger.info(f"   输出文件: {output_file.absolute()}")

            # 导出镜像
            with open(output_file, "wb") as f:
                # 使用低级API导出，支持进度显示
                image_data = self.client.api.get_image(image_name)

                total_size = 0
                chunk_count = 0

                for chunk in image_data:
                    f.write(chunk)
                    total_size += len(chunk)
                    chunk_count += 1

                    # 每100个chunk显示一次进度
                    if chunk_count % 100 == 0:
                        size_mb = total_size / (1024 * 1024)
                        print(f"   📥 已导出: {size_mb:.1f} MB", end="\r")

            # 获取最终文件大小
            final_size = output_file.stat().st_size
            size_mb = final_size / (1024 * 1024)

            logger.info(f"✅ 镜像导出成功!")
            logger.info(f"   📁 文件路径: {output_file.absolute()}")
            logger.info(f"   📊 文件大小: {size_mb:.1f} MB")

            # 显示使用提示
            print(f"\n💡 使用方法:")
            print(f"   📤 传输文件: scp {output_file.name} user@server:/path/")
            print(f"   📥 加载镜像: docker load < {output_file.name}")
            print(f"   📥 或者: docker load -i {output_file.name}")

            return True

        except Exception as e:
            logger.error(f"镜像导出失败: {e}")
            return False
