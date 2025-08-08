"""
文件预览生成模块
Author: DiChen
Date: 2025-07-31
"""

import os
import shutil
import threading
from typing import Optional, Tuple
import matplotlib
matplotlib.use('Agg')  # 使用非交互式后端，避免GUI线程问题
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
import logging

# 设置日志
logger = logging.getLogger(__name__)

# 全局matplotlib线程锁，确保在多线程环境中matplotlib调用的安全性
_matplotlib_lock = threading.Lock()


def matplotlib_thread_safe(func):
    """装饰器：确保matplotlib调用的线程安全性"""
    def wrapper(*args, **kwargs):
        with _matplotlib_lock:
            return func(*args, **kwargs)
    return wrapper


class PreviewGenerator:
    """文件预览生成器"""

    # 支持预览的地理数据文件扩展名
    SUPPORTED_GEO_EXTENSIONS = {
        ".tif",
        ".tiff",
        ".nc",
        ".hdf",
        ".h5",
        ".shp",
        ".geojson",
        ".kml",
        ".json",
    }

    # 支持预览的图像文件扩展名
    SUPPORTED_IMAGE_EXTENSIONS = {
        ".png",
        ".jpg",
        ".jpeg",
        ".bmp",
        ".gif",
        ".tiff",
        ".tif",
    }

    def __init__(self, preview_dir: Optional[str] = None):
        """
        初始化预览生成器

        Args:
            preview_dir: 预览文件目录，如果为None则使用当前目录下的preview文件夹
        """
        if preview_dir is None:
            self.preview_dir = os.path.join(os.getcwd(), "preview")
        else:
            self.preview_dir = preview_dir

        # 确保预览目录存在
        os.makedirs(self.preview_dir, exist_ok=True)

    def clear_preview_dir(self):
        """清空预览目录"""
        try:
            if os.path.exists(self.preview_dir):
                shutil.rmtree(self.preview_dir)
                os.makedirs(self.preview_dir, exist_ok=True)
                logger.info(f"已清空预览目录: {self.preview_dir}")
        except Exception as e:
            logger.error(f"清空预览目录失败: {e}")

    def _convert_png_to_webp(self, png_path: str, webp_path: str):
        """将PNG文件转换为WebP格式"""
        try:
            with Image.open(png_path) as img:
                img.save(webp_path, "WEBP", quality=85, method=6)
            # 删除临时PNG文件
            if os.path.exists(png_path):
                os.remove(png_path)
        except Exception as e:
            logger.error(f"PNG转WebP失败: {e}")
            # 如果转换失败，尝试直接重命名PNG文件
            if os.path.exists(png_path):
                png_fallback = webp_path.replace(".webp", ".png")
                os.rename(png_path, png_fallback)
                return png_fallback
        return webp_path

    def can_preview(self, file_path: str) -> bool:
        """
        检查文件是否可以生成预览

        Args:
            file_path: 文件路径

        Returns:
            bool: 是否可以预览
        """
        if not os.path.exists(file_path):
            return False

        ext = os.path.splitext(file_path)[1].lower()
        return ext in (self.SUPPORTED_GEO_EXTENSIONS | self.SUPPORTED_IMAGE_EXTENSIONS)

    def generate_preview(
        self, file_path: str, max_size: Tuple[int, int] = (800, 600), bands_config=None,
        workspace_dir: Optional[str] = None
    ) -> Optional[str]:
        """
        生成文件预览图

        Args:
            file_path: 文件路径
            max_size: 预览图最大尺寸 (width, height)
            bands_config: 波段配置（用于多光谱数据）
            workspace_dir: 工作空间目录，如果提供则在该目录生成preview

        Returns:
            str: 预览图路径，如果生成失败返回None
        """
        try:
            if not self.can_preview(file_path):
                return None

            ext = os.path.splitext(file_path)[1].lower()

            # 确定预览图存储目录
            if workspace_dir:
                # 在隔离工作空间中创建preview子目录
                preview_dir = os.path.join(workspace_dir, "preview")
                os.makedirs(preview_dir, exist_ok=True)
            else:
                # 使用全局preview目录（向后兼容）
                preview_dir = self.preview_dir

            # 生成预览图文件名
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            preview_path = os.path.join(preview_dir, f"{base_name}_preview.webp")

            # 根据文件类型生成预览
            if ext in {".tif", ".tiff"}:
                # 智能处理TIFF文件
                return self._generate_tiff_preview(file_path, preview_path, max_size, bands_config)
            elif ext in self.SUPPORTED_IMAGE_EXTENSIONS:
                return self._generate_image_preview(file_path, preview_path, max_size)
            elif ext in {".nc"}:
                return self._generate_netcdf_preview(file_path, preview_path, max_size)
            elif ext in {".hdf", ".h5"}:
                return self._generate_hdf_preview(file_path, preview_path, max_size)
            elif ext in {".shp"}:
                return self._generate_shapefile_preview(
                    file_path, preview_path, max_size
                )
            elif ext in {".kml"}:
                return self._generate_kml_preview(file_path, preview_path, max_size)
            else:
                return None

        except Exception as e:
            logger.error(f"生成预览失败 {file_path}: {e}")
            return None

    def _generate_image_preview(
        self, file_path: str, preview_path: str, max_size: Tuple[int, int]
    ) -> str:
        """生成普通图像文件预览"""
        try:
            with Image.open(file_path) as img:
                # 转换色彩模式以确保兼容性
                if img.mode in ("CMYK", "LAB"):
                    img = img.convert("RGB")
                elif img.mode in ("LA", "PA"):
                    img = img.convert("RGBA")
                elif img.mode == "P":
                    img = img.convert("RGBA")
                elif img.mode == "L":
                    img = img.convert("RGB")
                elif img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGB")

                # 计算缩放比例
                img.thumbnail(max_size, Image.Resampling.LANCZOS)

                # 保存为WebP格式，质量设为85
                img.save(preview_path, "WEBP", quality=85, method=6)
                return preview_path
        except Exception as e:
            logger.error(f"生成图像预览失败: {e}")
            return self._generate_error_preview(preview_path, "图像文件读取失败")

    def _generate_tiff_preview(
        self, file_path: str, preview_path: str, max_size: Tuple[int, int], bands_config=None
    ) -> str:
        """智能处理TIFF文件预览（GeoTIFF或普通TIFF）"""
        # 首先尝试用rasterio处理（适用于GeoTIFF）
        try:
            return self._generate_geotiff_preview(file_path, preview_path, max_size, bands_config)
        except ImportError:
            # rasterio未安装，尝试用PIL处理
            logger.info("rasterio未安装，尝试用PIL处理TIFF文件")
            return self._generate_image_preview(file_path, preview_path, max_size)
        except Exception as e:
            # GeoTIFF处理失败，尝试用PIL处理
            logger.info(f"GeoTIFF处理失败，尝试用PIL处理: {e}")
            try:
                return self._generate_image_preview(file_path, preview_path, max_size)
            except Exception as pil_error:
                logger.error(f"PIL处理TIFF也失败: {pil_error}")
                return self._generate_error_preview(
                    preview_path, f"TIFF文件处理失败: {str(pil_error)}"
                )

    def _normalize_and_clip(self, channel, low_percentile=0.5, high_percentile=99.5):
        """异常值剔除和归一化处理"""
        # 计算分位数阈值
        low = np.percentile(channel, low_percentile)
        high = np.percentile(channel, high_percentile)
        
        # 剔除异常值（限制在 low ~ high 之间）
        channel = np.clip(channel, low, high)
        
        # 归一化
        if high > low:
            return (channel - low) / (high - low)
        else:
            return np.zeros_like(channel)

    @matplotlib_thread_safe
    def _generate_geotiff_preview(
        self, file_path: str, preview_path: str, max_size: Tuple[int, int], bands_config=None
    ) -> str:
        """生成GeoTIFF文件预览"""
        try:
            import rasterio

            with rasterio.open(file_path) as src:
                # 默认RGB波段顺序 [3, 2, 1] (基于1的索引)
                if bands_config is None:
                    bands_config = [3, 2, 1]
                
                # 检查是否有足够的波段
                if src.count >= max(bands_config):
                    # 多波段RGB合成
                    try:
                        # 读取指定波段 (转换为基于0的索引)
                        r = src.read(bands_config[0])  # Red
                        g = src.read(bands_config[1])  # Green  
                        b = src.read(bands_config[2])  # Blue

                        # 异常值剔除和归一化
                        r_norm = self._normalize_and_clip(r)
                        g_norm = self._normalize_and_clip(g)
                        b_norm = self._normalize_and_clip(b)

                        # 组成RGB图像
                        rgb = np.dstack((r_norm, g_norm, b_norm))
                        
                    except Exception:
                        # 如果波段读取失败，使用前三个波段
                        data = src.read()[:3]
                        r_norm = self._normalize_and_clip(data[0])
                        g_norm = self._normalize_and_clip(data[1]) if data.shape[0] > 1 else r_norm
                        b_norm = self._normalize_and_clip(data[2]) if data.shape[0] > 2 else r_norm
                        rgb = np.dstack((r_norm, g_norm, b_norm))
                        
                else:
                    # 单波段处理
                    band_data = src.read(1)
                    rgb = self._normalize_and_clip(band_data)

                # 创建纯净的图像显示（无坐标轴、标题等）
                _, ax = plt.subplots(figsize=(max_size[0] / 100, max_size[1] / 100))
                
                if len(rgb.shape) == 3:
                    ax.imshow(rgb)
                else:
                    ax.imshow(rgb, cmap="viridis")
                
                # 去除所有坐标轴、标题、标签
                ax.set_xticks([])
                ax.set_yticks([])
                ax.axis('off')
                
                # 保存纯净图像
                temp_png_path = preview_path.replace(".webp", "_temp.png")
                plt.savefig(temp_png_path, dpi=100, bbox_inches='tight', 
                           pad_inches=0, facecolor='white')
                plt.close()

                # 转换PNG为WebP
                self._convert_png_to_webp(temp_png_path, preview_path)
                return preview_path

        except ImportError:
            return self._generate_info_preview(
                preview_path, "GeoTIFF文件", "需要安装rasterio库"
            )
        except Exception as e:
            logger.error(f"生成GeoTIFF预览失败: {e}")
            return self._generate_error_preview(preview_path, f"GeoTIFF文件处理失败: {str(e)}")

    @matplotlib_thread_safe
    def _generate_netcdf_preview(
        self, file_path: str, preview_path: str, max_size: Tuple[int, int]
    ) -> str:
        """生成NetCDF文件预览"""
        try:
            import xarray as xr

            ds = xr.open_dataset(file_path)

            # 找到第一个二维或三维数据变量
            data_vars = [var for var in ds.data_vars if len(ds[var].dims) >= 2]

            if not data_vars:
                return self._generate_info_preview(
                    preview_path, "NetCDF文件", "未找到可视化的数据变量"
                )

            var_name = data_vars[0]
            data_var = ds[var_name]

            _, ax = plt.subplots(figsize=(max_size[0] / 100, max_size[1] / 100))

            # 如果是三维数据，取第一个时间切片
            if len(data_var.dims) > 2:
                data_var = data_var.isel({data_var.dims[0]: 0})

            # 绘制数据
            data_var.plot(ax=ax, cmap="viridis", add_colorbar=True)
            ax.set_title(f"NetCDF: {var_name}")

            plt.tight_layout()
            # 先保存为PNG，然后转换为WebP
            temp_png_path = preview_path.replace(".webp", "_temp.png")
            plt.savefig(temp_png_path, dpi=100, bbox_inches="tight")
            plt.close()
            ds.close()

            # 转换PNG为WebP
            self._convert_png_to_webp(temp_png_path, preview_path)

            return preview_path

        except ImportError:
            return self._generate_info_preview(
                preview_path, "NetCDF文件", "需要安装xarray库"
            )
        except Exception as e:
            logger.error(f"生成NetCDF预览失败: {e}")
            return self._generate_error_preview(preview_path, "NetCDF文件读取失败")

    @matplotlib_thread_safe
    def _generate_hdf_preview(
        self, file_path: str, preview_path: str, max_size: Tuple[int, int]
    ) -> str:
        """生成HDF文件预览"""
        try:
            import h5py

            with h5py.File(file_path, "r") as f:
                # 递归查找数据集
                datasets = []

                def find_datasets(name, obj):
                    if isinstance(obj, h5py.Dataset) and len(obj.shape) >= 2:
                        datasets.append((name, obj.shape, obj.dtype))

                f.visititems(find_datasets)

                if not datasets:
                    return self._generate_info_preview(
                        preview_path, "HDF文件", "未找到可视化的数据集"
                    )

                # 取第一个数据集进行可视化
                dataset_name = datasets[0][0]
                data = f[dataset_name][:]

                _, ax = plt.subplots(figsize=(max_size[0] / 100, max_size[1] / 100))

                # 如果是三维数据，取第一个切片
                if len(data.shape) > 2:
                    data = data[0] if data.shape[0] < data.shape[-1] else data[..., 0]

                im = ax.imshow(data, cmap="viridis")
                ax.set_title(f"HDF: {dataset_name}")
                plt.colorbar(im)

                plt.tight_layout()
                # 先保存为PNG，然后转换为WebP
                temp_png_path = preview_path.replace(".webp", "_temp.png")
                plt.savefig(temp_png_path, dpi=100, bbox_inches="tight")
                plt.close()

                # 转换PNG为WebP
                self._convert_png_to_webp(temp_png_path, preview_path)

                return preview_path

        except ImportError:
            return self._generate_info_preview(
                preview_path, "HDF文件", "需要安装h5py库"
            )
        except Exception as e:
            logger.error(f"生成HDF预览失败: {e}")
            return self._generate_error_preview(preview_path, "HDF文件读取失败")

    @matplotlib_thread_safe
    def _generate_shapefile_preview(
        self, file_path: str, preview_path: str, max_size: Tuple[int, int]
    ) -> str:
        """生成Shapefile预览"""
        try:
            import geopandas as gpd

            gdf = gpd.read_file(file_path)

            _, ax = plt.subplots(figsize=(max_size[0] / 100, max_size[1] / 100))
            gdf.plot(ax=ax, alpha=0.7, edgecolor="black")
            ax.set_title(f"Shapefile: {os.path.basename(file_path)}")
            ax.set_xlabel(f"CRS: {gdf.crs}")

            plt.tight_layout()
            # 先保存为PNG，然后转换为WebP
            temp_png_path = preview_path.replace(".webp", "_temp.png")
            plt.savefig(temp_png_path, dpi=100, bbox_inches="tight")
            plt.close()

            # 转换PNG为WebP
            self._convert_png_to_webp(temp_png_path, preview_path)

            return preview_path

        except ImportError:
            return self._generate_info_preview(
                preview_path, "Shapefile", "需要安装geopandas库"
            )
        except Exception as e:
            logger.error(f"生成Shapefile预览失败: {e}")
            return self._generate_error_preview(preview_path, "Shapefile读取失败")

    @matplotlib_thread_safe
    def _generate_kml_preview(
        self, file_path: str, preview_path: str, max_size: Tuple[int, int]
    ) -> str:
        """生成KML文件预览"""
        try:
            import geopandas as gpd

            # 启用KML驱动
            gpd.io.file.fiona.drvsupport.supported_drivers["KML"] = "rw"
            gdf = gpd.read_file(file_path, driver="KML")

            _, ax = plt.subplots(figsize=(max_size[0] / 100, max_size[1] / 100))
            gdf.plot(ax=ax, alpha=0.7, edgecolor="black")
            ax.set_title(f"KML: {os.path.basename(file_path)}")
            ax.set_xlabel(f"CRS: {gdf.crs}")

            plt.tight_layout()
            # 先保存为PNG，然后转换为WebP
            temp_png_path = preview_path.replace(".webp", "_temp.png")
            plt.savefig(temp_png_path, dpi=100, bbox_inches="tight")
            plt.close()

            # 转换PNG为WebP
            self._convert_png_to_webp(temp_png_path, preview_path)

            return preview_path

        except ImportError:
            return self._generate_info_preview(
                preview_path, "KML文件", "需要安装geopandas库"
            )
        except Exception as e:
            logger.error(f"生成KML预览失败: {e}")
            return self._generate_error_preview(preview_path, "KML文件读取失败")

    @matplotlib_thread_safe
    def _generate_info_preview(
        self, preview_path: str, file_type: str, message: str
    ) -> str:
        """生成信息提示预览图"""
        _, ax = plt.subplots(figsize=(8, 6))
        ax.text(
            0.5,
            0.5,
            f"{file_type}\n\n{message}",
            ha="center",
            va="center",
            fontsize=14,
            bbox=dict(boxstyle="round,pad=0.3", facecolor="lightblue"),
        )
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")

        plt.tight_layout()
        # 先保存为PNG，然后转换为WebP
        temp_png_path = preview_path.replace(".webp", "_temp.png")
        plt.savefig(temp_png_path, dpi=100, bbox_inches="tight")
        plt.close()

        # 转换PNG为WebP
        return self._convert_png_to_webp(temp_png_path, preview_path)

    @matplotlib_thread_safe
    def _generate_error_preview(self, preview_path: str, error_message: str) -> str:
        """生成错误提示预览图"""
        _, ax = plt.subplots(figsize=(8, 6))
        ax.text(
            0.5,
            0.5,
            f"⚠️ 预览生成失败\n\n{error_message}",
            ha="center",
            va="center",
            fontsize=14,
            bbox=dict(boxstyle="round,pad=0.3", facecolor="lightcoral"),
        )
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")

        plt.tight_layout()
        # 先保存为PNG，然后转换为WebP
        temp_png_path = preview_path.replace(".webp", "_temp.png")
        plt.savefig(temp_png_path, dpi=100, bbox_inches="tight")
        plt.close()

        # 转换PNG为WebP
        return self._convert_png_to_webp(temp_png_path, preview_path)
