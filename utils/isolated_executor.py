"""
智能工作空间隔离执行器
用于支持并发模型执行，自动检测大文件并创建符号链接
"""

from cmath import log
import uuid
import shutil
import subprocess
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Dict, Set
from .logger import get_logger

# 初始化日志
logger = get_logger(__name__)


class IsolatedModelExecutor:
    def __init__(
        self, max_workers: int = 5, large_file_threshold: int = 200 * 1024 * 1024
    ):
        """
        初始化智能工作空间隔离执行器

        Args:
            max_workers: 最大并发worker数量
            large_file_threshold: 大文件阈值（字节），超过此大小的文件将创建符号链接
        """
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.large_file_threshold = large_file_threshold
        # 文件大小缓存，避免重复计算
        self._file_size_cache: Dict[str, int] = {}
        # 大文件扩展名模式（通常模型权重文件）
        self._large_file_extensions: Set[str] = {
            ".pt",
            ".pth",
            ".ckpt",
            ".pkl",
            ".h5",
            ".hdf5",
            ".weights",
            ".bin",
            ".safetensors",
            ".tar",
            ".zip",
            ".7z",
            ".rar",
        }

    def get_file_size(self, file_path: str) -> int:
        """
        获取文件大小（字节），使用缓存机制避免重复I/O操作

        Args:
            file_path: 文件路径

        Returns:
            文件大小（字节）
        """
        # 规范化路径作为缓存键
        abs_path = os.path.abspath(file_path)

        # 检查缓存
        if abs_path in self._file_size_cache:
            return self._file_size_cache[abs_path]

        try:
            # 获取文件状态
            stat_info = os.stat(file_path)
            file_size = stat_info.st_size

            # 缓存结果
            self._file_size_cache[abs_path] = file_size
            return file_size
        except OSError as e:
            logger.debug("无法获取文件大小 %s: %s", file_path, str(e))
            # 缓存错误结果避免重复尝试
            self._file_size_cache[abs_path] = 0
            return 0

    def _is_likely_large_file(self, file_path: str) -> bool:
        """
        基于文件扩展名快速预判是否可能是大文件

        Args:
            file_path: 文件路径

        Returns:
            True如果可能是大文件
        """
        _, ext = os.path.splitext(file_path.lower())
        return ext in self._large_file_extensions

    def _should_link_file(self, file_path: str) -> bool:
        """
        判断文件是否应该使用符号链接

        Args:
            file_path: 文件路径

        Returns:
            True如果应该使用符号链接
        """
        # 快速预检查：如果扩展名表明可能是大文件，优先检查
        if self._is_likely_large_file(file_path):
            file_size = self.get_file_size(file_path)
            return file_size > self.large_file_threshold

        # 对于其他文件，仍然检查大小
        file_size = self.get_file_size(file_path)
        return file_size > self.large_file_threshold

    def copy_directory_with_smart_linking(self, src_dir: str, dst_dir: str) -> None:
        """
        智能复制目录：大文件用符号链接，小文件直接复制

        Args:
            src_dir: 源目录路径
            dst_dir: 目标目录路径
        """
        if not os.path.exists(src_dir):
            logger.warning("源目录不存在: %s", src_dir)
            return

        # 确保目标目录存在
        os.makedirs(dst_dir, exist_ok=True)

        large_files_count = 0
        small_files_count = 0
        total_large_size = 0
        total_small_size = 0

        logger.debug("开始智能复制目录: %s -> %s", src_dir, dst_dir)

        for root, dirs, files in os.walk(src_dir):
            # 创建相应的子目录结构
            for dir_name in dirs:
                src_subdir = os.path.join(root, dir_name)
                rel_path = os.path.relpath(src_subdir, src_dir)
                dst_subdir = os.path.join(dst_dir, rel_path)
                os.makedirs(dst_subdir, exist_ok=True)

            # 处理文件
            for file_name in files:
                src_file = os.path.join(root, file_name)
                rel_path = os.path.relpath(src_file, src_dir)
                dst_file = os.path.join(dst_dir, rel_path)

                # 确保目标文件的父目录存在
                os.makedirs(os.path.dirname(dst_file), exist_ok=True)

                # 使用优化的文件检查逻辑
                if self._should_link_file(src_file):
                    file_size = self.get_file_size(
                        src_file
                    )  # 已在_should_link_file中缓存
                    # 大文件：创建符号链接
                    abs_source = os.path.abspath(src_file)
                    try:
                        os.symlink(abs_source, dst_file)
                        large_files_count += 1
                        total_large_size += file_size
                        logger.debug(
                            "大文件符号链接: %s (%.1fMB)",
                            rel_path,
                            file_size / (1024 * 1024),
                        )
                    except OSError as e:
                        logger.warning(
                            "符号链接创建失败: %s, 错误: %s", rel_path, str(e)
                        )
                        # 如果符号链接失败，回退到复制
                        try:
                            shutil.copy2(src_file, dst_file)
                            logger.info("回退到复制: %s", rel_path)
                        except Exception as copy_e:
                            logger.error(
                                "文件复制也失败: %s, 错误: %s", rel_path, str(copy_e)
                            )
                else:
                    # 小文件：直接复制
                    file_size = self.get_file_size(src_file)  # 获取文件大小用于统计
                    try:
                        shutil.copy2(src_file, dst_file)
                        small_files_count += 1
                        total_small_size += file_size
                        if file_size > 1024:
                            logger.debug(
                                "小文件复制: %s (%.1fKB)", rel_path, file_size / 1024
                            )
                        else:
                            logger.debug("小文件复制: %s (%dB)", rel_path, file_size)
                    except Exception as e:
                        logger.error("文件复制失败: %s, 错误: %s", rel_path, str(e))

        # 输出统计信息
        logger.info("复制统计:")
        logger.info(
            "  大文件 (符号链接): %d 个, 总大小: %.1fMB",
            large_files_count,
            total_large_size / (1024 * 1024),
        )
        logger.info(
            "  小文件 (直接复制): %d 个, 总大小: %.1fKB",
            small_files_count,
            total_small_size / 1024,
        )
        logger.info("  节省存储空间: %.1fMB", total_large_size / (1024 * 1024))

    def prepare_workspace(self, session_id: str) -> str:
        """
        预创建隔离工作空间

        Args:
            session_id: 会话ID

        Returns:
            工作空间路径
        """
        workspace = f"workspace_{session_id}"

        logger.info("正在为会话 %s 准备工作空间...", session_id)

        # 创建基础目录结构
        os.makedirs(workspace, exist_ok=True)
        os.makedirs(f"{workspace}/outputs", exist_ok=True)

        # 智能复制model目录
        model_src = "model"
        model_dst = f"{workspace}/model"

        if os.path.exists(model_src):
            logger.debug("复制model目录: %s -> %s", model_src, model_dst)
            self.copy_directory_with_smart_linking(model_src, model_dst)
        else:
            logger.warning("model目录不存在: %s", model_src)

        logger.info("工作空间 %s 准备完成", workspace)
        return workspace

    def execute_model_isolated(
        self, inputs: List[str], cmd_template: Optional[List[str]] = None
    ) -> str:
        """
        在隔离的工作空间中执行模型

        Args:
            inputs: 输入参数列表
            cmd_template: 自定义命令模板，如果为None则使用默认模板

        Returns:
            输出目录路径
        """
        session_id = str(uuid.uuid4())[:8]
        workspace = self.prepare_workspace(session_id)

        try:
            # 移除cmd_template列表中的None值
            cmd = [arg for arg in cmd_template if arg is not None]

            logger.info("在工作空间 %s 中执行模型...", workspace)
            logger.info("执行命令: %s", " ".join(cmd))

            # 在工作空间中执行命令
            result = subprocess.run(
                cmd, cwd=workspace, check=True, capture_output=True, text=True
            )
            logger.info("模型执行成功")
            if result.stdout:
                logger.debug("标准输出: %s", result.stdout)

            output_dir = f"{workspace}/outputs"

            # 检查输出目录是否有文件
            if os.path.exists(output_dir):
                output_files = os.listdir(output_dir)
                if output_files:
                    logger.debug("输出文件: %s", output_files)
                else:
                    logger.warning("输出目录为空")
            else:
                logger.warning("输出目录不存在")

            return output_dir

        except subprocess.CalledProcessError as e:
            logger.error("模型执行失败: %s", str(e))
            if e.stdout:
                logger.debug("标准输出: %s", e.stdout)
            if e.stderr:
                logger.debug("标准错误: %s", e.stderr)
            # 保留工作空间用于调试
            logger.info("保留工作空间用于调试: %s", workspace)
            raise e
        except Exception as e:
            logger.error("未知错误: %s", str(e))
            logger.debug("清理失败的工作空间: %s", workspace)
            shutil.rmtree(workspace, ignore_errors=True)
            raise e

    def execute_model_async(
        self, inputs: List[str], cmd_template: Optional[List[str]] = None
    ):
        """
        异步执行模型（返回Future对象）

        Args:
            inputs: 输入参数列表
            cmd_template: 自定义命令模板

        Returns:
            Future对象，可以用于获取执行结果
        """
        return self.executor.submit(self.execute_model_isolated, inputs, cmd_template)

    def get_workspace_info(self, workspace: str) -> str:
        """
        获取工作空间信息（调试用）

        Args:
            workspace: 工作空间路径

        Returns:
            工作空间信息字符串
        """
        if not os.path.exists(workspace):
            return "❌ 工作空间不存在"

        info = [f"📁 工作空间: {workspace}"]

        # 检查outputs目录
        outputs_dir = f"{workspace}/outputs"
        if os.path.exists(outputs_dir):
            output_files = os.listdir(outputs_dir)
            if output_files:
                info.append(f"📤 输出文件 ({len(output_files)} 个):")
                for file_name in output_files[:10]:  # 最多显示10个文件
                    file_path = os.path.join(outputs_dir, file_name)
                    size = self.get_file_size(file_path)
                    if size > 1024 * 1024:
                        info.append(f"   📄 {file_name} ({size/(1024*1024):.1f}MB)")
                    else:
                        info.append(f"   📄 {file_name} ({size/1024:.1f}KB)")
                if len(output_files) > 10:
                    info.append(f"   ... 还有 {len(output_files) - 10} 个文件")
            else:
                info.append("📤 输出目录为空")
        else:
            info.append("❌ 输出目录不存在")

        # 检查model目录
        model_dir = f"{workspace}/model"
        if os.path.exists(model_dir):
            info.append("📁 Model目录文件:")
            for root, dirs, files in os.walk(model_dir):
                for file_name in files:
                    file_path = os.path.join(root, file_name)
                    rel_path = os.path.relpath(file_path, workspace)

                    if os.path.islink(file_path):
                        target = os.readlink(file_path)
                        size = self.get_file_size(target)
                        info.append(
                            f"   🔗 {rel_path} -> {target} ({size/(1024*1024):.1f}MB)"
                        )
                    else:
                        size = self.get_file_size(file_path)
                        if size > 1024:
                            info.append(f"   📄 {rel_path} ({size/1024:.1f}KB)")
                        else:
                            info.append(f"   📄 {rel_path} ({size}B)")

        return "\n".join(info)

    def cleanup_old_workspaces(self, max_age_hours: int = 24) -> int:
        """
        定期清理旧的工作空间

        Args:
            max_age_hours: 最大保留时间（小时）

        Returns:
            清理的工作空间数量
        """
        current_time = time.time()
        cleaned_count = 0

        logger.info("开始清理超过 %d 小时的旧工作空间...", max_age_hours)

        try:
            for item in os.listdir("."):
                if item.startswith("workspace_"):
                    workspace_path = os.path.join(".", item)
                    if os.path.isdir(workspace_path):
                        try:
                            creation_time = os.path.getctime(workspace_path)
                            age_hours = (current_time - creation_time) / 3600

                            if age_hours > max_age_hours:
                                logger.debug(
                                    "清理旧工作空间: %s (年龄: %.1f小时)",
                                    workspace_path,
                                    age_hours,
                                )
                                shutil.rmtree(workspace_path, ignore_errors=True)
                                cleaned_count += 1
                            else:
                                logger.debug(
                                    "保留工作空间: %s (年龄: %.1f小时)",
                                    workspace_path,
                                    age_hours,
                                )
                        except Exception as e:
                            logger.error(
                                "清理工作空间失败: %s, 错误: %s", workspace_path, str(e)
                            )
        except Exception as e:
            logger.error("扫描工作空间目录失败: %s", str(e))

        logger.info("清理完成，共清理了 %d 个工作空间", cleaned_count)
        return cleaned_count

    def shutdown(self):
        """关闭执行器"""
        logger.info("正在关闭隔离执行器...")
        self.executor.shutdown(wait=True)
        # 清理缓存
        self._file_size_cache.clear()
        logger.info("隔离执行器已关闭")
