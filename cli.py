"""
inoyb命令行工具
"""

import sys
import argparse
from pathlib import Path
from typing import Optional
from datetime import datetime
from .docker.builder import DockerBuilder
from .docker.manager import DockerManager
from .docker.config import DockerConfig
from .runner.local import LocalRunner
from .runner.container import ContainerRunner
from .utils.logger import get_logger

logger = get_logger(__name__)


def _print_images_table(images):
    """打印镜像信息表格 - 自适应列宽"""
    if not images:
        return

    # 准备表格数据
    headers = ["Tag", "Size", "Model Size", "Creation Time"]
    rows = []

    for img in images:
        # 处理镜像名称（移除inoyb/前缀）
        tag = img["name"]

        # 格式化大小
        size_bytes = img.get("size", 0)
        if size_bytes > 1024 * 1024 * 1024:  # GiB
            size_str = f"{size_bytes / (1024**3):.2f} GiB"
        elif size_bytes > 1024 * 1024:  # MiB
            size_str = f"{size_bytes / (1024**2):.2f} MiB"
        elif size_bytes > 1024:  # KiB
            size_str = f"{size_bytes / 1024:.2f} KiB"
        else:
            size_str = f"{size_bytes} B" if size_bytes > 0 else "0.00 B"

        # 格式化模型大小
        model_size_bytes = img.get("model_size", 0)
        if model_size_bytes > 1024 * 1024 * 1024:  # GiB
            model_size = f"{model_size_bytes / (1024**3):.2f} GiB"
        elif model_size_bytes > 1024 * 1024:  # MiB
            model_size = f"{model_size_bytes / (1024**2):.2f} MiB"
        elif model_size_bytes > 1024:  # KiB
            model_size = f"{model_size_bytes / 1024:.2f} KiB"
        elif model_size_bytes > 0:
            model_size = f"{model_size_bytes} B"
        else:
            model_size = "0.00 B"

        # 格式化创建时间
        created_time = img.get("created", "")
        if created_time:
            try:
                # Docker API返回的时间格式通常是ISO格式
                if "T" in created_time:
                    dt = datetime.fromisoformat(created_time.replace("Z", "+00:00"))
                    creation_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    creation_time = created_time
            except:
                creation_time = created_time
        else:
            creation_time = "Unknown"

        rows.append([tag, size_str, model_size, creation_time])

    # 计算每列的最大宽度
    col_widths = []
    for i, header in enumerate(headers):
        # 计算表头和所有行中该列的最大宽度
        max_width = len(header)
        for row in rows:
            if i < len(row):
                max_width = max(max_width, len(str(row[i])))
        col_widths.append(max_width)

    # 列间间隔
    separator = "   "  # 3个字符间隔

    # 打印表头（加粗）
    header_line = separator.join(
        f"{headers[i]:<{col_widths[i]}}" for i in range(len(headers))
    )
    # 使用ANSI转义序列加粗表头
    bold_header = f"\033[1m{header_line}\033[0m"
    print(bold_header)

    # 打印分隔线
    total_width = sum(col_widths) + len(separator) * (len(headers) - 1)
    print("-" * total_width)

    # 打印数据行
    for row in rows:
        row_line = separator.join(
            f"{row[i] if i < len(row) else '':<{col_widths[i]}}"
            for i in range(len(headers))
        )
        print(row_line)

    print()


def cmd_build(args):
    """构建Docker镜像"""
    use_gpu = getattr(args, "gpu", False)
    registry = getattr(args, "registry", None)
    base_image = getattr(args, "base_image", None)

    version_desc = "GPU版本" if use_gpu else "CPU版本"
    print(f"🚀 开始构建Docker镜像 ({version_desc})...")

    try:
        # 检查Docker连接
        print("🔍 检查Docker环境...")
        builder = DockerBuilder()

        image_name, image_id = builder.build_image(
            args.path, use_gpu, registry, base_image
        )

        print(f"\n🎉 镜像构建成功!")
        print(f"   📦 镜像名称: {image_name}")
        print(f"   🆔 镜像ID: {image_id[:12]}")
        print(f"   🌍 地理空间支持: 已启用 (rasterio/GDAL/PROJ/GEOS)")
        if use_gpu:
            print(f"   🔥 GPU支持: 已启用")
        print(f"\n💡 下一步操作:")
        print(f"   📤 推送镜像: inoyb push")
        print(f"   📋 查看镜像: inoyb images list")

        deploy_cmd = "inoyb deploy --gpu" if use_gpu else "inoyb deploy"
        print(f"   🚀 一键部署: {deploy_cmd}")

    except ImportError as e:
        print(f"❌ 依赖缺失: {e}")
        print("💡 请安装Docker Python库: pip install docker>=7.0.0")
        sys.exit(1)
    except Exception as e:
        error_msg = str(e)
        if "Cannot connect to the Docker daemon" in error_msg:
            print("❌ 无法连接Docker服务")
            print("💡 请确保Docker已启动并可访问")
            print("   - macOS: 启动Docker Desktop")
            print("   - Linux: sudo systemctl start docker")
        elif any(
            keyword in error_msg.lower()
            for keyword in [
                "tls: bad record mac",
                "manifest unknown",
                "connection reset",
                "timeout",
                "registry-1.docker.io",
            ]
        ):
            # 网络相关错误已经在 DockerBuilder 中处理了，这里只需要简单提示
            print("❌ 网络连接问题导致构建失败")
            print("💡 详细的解决方案请查看上方输出")
        else:
            print(f"❌ 构建失败: {e}")
        sys.exit(1)


def cmd_push(args):
    """推送Docker镜像"""
    print("📤 开始推送镜像...")

    try:
        manager = DockerManager()

        if args.image:
            print(f"🏷️  指定镜像: {args.image}")
        else:
            print("🔍 查找最新镜像...")

        if manager.push_image(args.image):
            print("🎉 镜像推送成功!")
            print("\n💡 提示:")
            print("   镜像已推送到远程服务器")
            print("   可通过远程服务器部署运行")
        else:
            print("❌ 镜像推送失败!")
            sys.exit(1)

    except ImportError as e:
        print(f"❌ 依赖缺失: {e}")
        print("💡 请安装Docker Python库: pip install docker>=7.0.0")
        sys.exit(1)
    except Exception as e:
        error_msg = str(e)
        if "Cannot connect to the Docker daemon" in error_msg:
            print("❌ 无法连接本地Docker服务")
            print("💡 请确保Docker已启动")
        elif "无法连接到远程Docker服务器" in error_msg:
            print("❌ 无法连接远程Docker服务器")
            print("💡 请检查网络连接和服务器配置")
            print("   查看配置: inoyb config list")
        else:
            print(f"❌ 推送失败: {e}")
        sys.exit(1)


def cmd_images(args):
    """管理镜像"""
    try:
        builder = DockerBuilder()
        manager = DockerManager()
        if args.action == "list":
            if hasattr(args, "remote") and args.remote:
                # 列出远程镜像
                print("☁️  远程镜像:")
                try:
                    remote_images = manager.list_remote_images()
                    if not remote_images:
                        print("   (没有找到镜像或无法连接)")
                    else:
                        _print_images_table(remote_images)
                except:
                    print("   (无法连接到远程服务器)")
            else:
                # 列出本地镜像
                print("📦 本地镜像:")
                images = builder.list_local_images()
                if not images:
                    print("   (没有找到镜像)")
                else:
                    _print_images_table(images)

        elif args.action == "clean":
            if args.keep == 0:
                keep_count = 0
            if args.keep is None:
                keep_count = 3
            print(f"🧹 开始清理旧镜像 (保留最新 {keep_count} 个)...")
            removed = builder.cleanup_old_images(keep_count)
            if removed > 0:
                print(f"✅ 清理完成，删除了 {removed} 个旧镜像")
            else:
                print("ℹ️  没有需要清理的镜像")

        elif args.action == "rm":
            if not args.name:
                print("❌ 请指定要删除的镜像名称")
                print("💡 用法: inoyb images rm <镜像名称>")
                sys.exit(1)

            print(f"🗑️  正在删除镜像: {args.name}")
            if builder.remove_image(args.name):
                print(f"✅ 镜像删除成功: {args.name}")
            else:
                print(f"❌ 镜像删除失败: {args.name}")
                print("💡 请检查镜像名称是否正确")
                sys.exit(1)

        elif args.action == "prune":
            print("🧹 正在清理 Docker 构建缓存和无用容器...")
            if builder.cleanup_build_cache():
                print("✅ 清理完成")
                print("💡 这可能解决 Docker Desktop 日志查看问题")
            else:
                print("❌ 清理失败")
                sys.exit(1)

        elif args.action == "export":
            if not args.name:
                print("❌ 请指定要导出的镜像名称")
                print(
                    "💡 用法: inoyb images export <镜像名称> [-o 输出文件] [--path 导出目录]"
                )
                print("💡 示例: inoyb images export inoyb/my-model:abc123")
                print(
                    "💡 示例: inoyb images export inoyb/my-model:abc123 --path ./exports"
                )
                sys.exit(1)

            output_path = getattr(args, "output", None)
            export_path = getattr(args, "path", None)

            print(f"📦 正在导出镜像: {args.name}")
            if export_path:
                print(f"   导出目录: {export_path}")
            else:
                print(f"   导出目录: 当前目录 (.)")
            if output_path:
                print(f"   文件名: {output_path}")
            else:
                print(f"   文件名: 自动生成")

            if builder.export_image(args.name, output_path, export_path):
                print("🎉 镜像导出成功!")
            else:
                print("❌ 镜像导出失败!")
                sys.exit(1)

    except Exception as e:
        print(f"❌ 操作失败: {e}")
        sys.exit(1)


def cmd_config(args):
    """配置管理"""
    try:
        config = DockerConfig()

        if args.action == "set":
            if args.key == "default":
                config.set_default_server()
                print("✅ 已切换回默认服务器")
            elif args.key == "docker.host":
                if not args.value:
                    print("❌ 请提供服务器地址")
                    sys.exit(1)
                config.set_docker_host(args.value)
                print(f"✅ Docker服务器已设置为: {args.value}")
            elif args.key == "registry.mirror":
                if not args.value:
                    print("❌ 请提供镜像加速地址")
                    sys.exit(1)
                config.set_registry_mirror(args.value)
                print(f"✅ 镜像加速已设置为: {args.value}")
            elif args.key == "registry.default":
                if not args.value:
                    print("❌ 请提供默认镜像仓库")
                    sys.exit(1)
                config.set_default_registry(args.value)
                print(f"✅ 默认镜像仓库已设置为: {args.value}")
            elif args.key.startswith("image.map."):
                # 镜像映射: image.map.python:3.12-slim=my-registry.com/python:3.12-slim
                if not args.value:
                    print("❌ 请提供映射目标镜像")
                    sys.exit(1)
                original_image = args.key[10:]  # 移除 "image.map." 前缀
                config.add_image_mapping(original_image, args.value)
                print(f"✅ 镜像映射已添加: {original_image} -> {args.value}")
            else:
                print(f"❌ 未知配置项: {args.key}")
                print("💡 支持的配置项:")
                print("   - default: 切换回默认服务器")
                print("   - docker.host <地址>: 设置Docker服务器地址")
                print("   - registry.mirror <地址>: 设置镜像加速地址")
                print("   - registry.default <地址>: 设置默认镜像仓库")
                print("   - image.map.<原镜像> <目标镜像>: 添加镜像映射")
                sys.exit(1)

        elif args.action == "list":
            print("📋 当前配置:")
            print(f"   Docker服务器: {config.get_docker_host()}")
            print(
                f"   使用默认服务器: {'是' if config.is_using_default_server() else '否'}"
            )
            print(f"   镜像仓库: {config.get_registry()}")
            print("   模板支持:")
            print("     - CPU版本 (默认) - 包含 rasterio/GDAL/PROJ/GEOS")
            print("     - GPU版本 (--gpu) - 包含 rasterio/GDAL/PROJ/GEOS + CUDA")

            # 显示镜像源配置
            base_config = config.get_base_image_config()
            print("   镜像源配置:")

            registry_mirror = base_config.get("registry_mirror")
            if registry_mirror:
                print(f"     - 镜像加速: {registry_mirror}")
            else:
                print("     - 镜像加速: 未设置")

            default_registry = base_config.get("default_registry")
            if default_registry:
                print(f"     - 默认仓库: {default_registry}")
            else:
                print("     - 默认仓库: 未设置")

            custom_mappings = base_config.get("custom_mappings", {})
            if custom_mappings:
                print("     - 镜像映射:")
                for original, target in custom_mappings.items():
                    print(f"       {original} -> {target}")
            else:
                print("     - 镜像映射: 未设置")

    except Exception as e:
        print(f"❌ 配置操作失败: {e}")
        sys.exit(1)


def cmd_check(args):
    """检查项目结构"""
    print("🔍 检查项目结构...")

    try:
        builder = DockerBuilder()
        mc_config, has_examples = builder.validate_project(args.path)

        print("✅ 项目结构检查通过!")
        print(f"   📋 模型名称: {mc_config['model_info']['name']}")
        print(f"   📁 包含examples: {'是' if has_examples else '否'}")
        print("\n📦 项目文件:")
        print("   ✅ gogogo.py")
        print("   ✅ mc.json")
        print("   ✅ requirements.txt")
        print("   ✅ model/")
        if has_examples:
            print("   ✅ examples/")

        print(f"\n💡 项目已准备就绪，可以执行:")
        print("   🔨 构建镜像: inoyb build")
        print("   🚀 一键部署: inoyb deploy")

    except Exception as e:
        print(f"❌ 项目结构检查失败: {e}")
        print("\n💡 请确保项目包含以下文件:")
        print("   - gogogo.py (模型服务启动文件)")
        print("   - mc.json (配置文件，包含model_info.name)")
        print("   - requirements.txt (依赖文件)")
        print("   - model/ (模型文件目录)")
        print("   - examples/ (可选，示例数据)")
        sys.exit(1)


def cmd_serve(args):
    """本地运行服务"""
    try:
        runner = LocalRunner()
        runner.run(
            port=args.port,
            host=args.host,
            reload=args.reload or args.dev,
            open_browser=args.open,
            verbose=args.verbose,
            project_path=args.path,
        )
    except ImportError as e:
        print(f"❌ 依赖缺失: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        sys.exit(1)


def cmd_run(args):
    """运行Docker镜像"""
    try:
        runner = ContainerRunner()

        # 解析环境变量
        env_vars = {}
        if hasattr(args, "env") and args.env:
            for env_pair in args.env:
                if "=" in env_pair:
                    key, value = env_pair.split("=", 1)
                    env_vars[key] = value
                else:
                    print(f"⚠️  忽略无效的环境变量格式: {env_pair}")

        # 解析卷挂载
        volumes = {}
        if hasattr(args, "volume") and args.volume:
            for volume_pair in args.volume:
                if ":" in volume_pair:
                    host_path, container_path = volume_pair.split(":", 1)
                    volumes[host_path] = container_path
                else:
                    print(f"⚠️  忽略无效的卷挂载格式: {volume_pair}")

        runner.run(
            image_name=args.image,
            port=args.port,
            daemon=args.daemon,
            remove=args.rm,
            interactive=args.interactive,
            name=args.name,
            env=env_vars,
            volumes=volumes,
            follow_logs=not args.daemon,
        )

    except ImportError as e:
        print(f"❌ 依赖缺失: {e}")
        print("💡 请安装Docker Python库: pip install docker>=7.0.0")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 运行失败: {e}")
        sys.exit(1)


def cmd_deploy(args):
    """一键构建并推送"""
    try:
        use_gpu = getattr(args, "gpu", False)
        registry = getattr(args, "registry", None)
        base_image = getattr(args, "base_image", None)

        version_desc = "GPU版本" if use_gpu else "CPU版本"
        print(f"🚀 开始部署流程 ({version_desc})...")

        # 构建镜像
        builder = DockerBuilder()
        image_name, _image_id = builder.build_image(
            args.path, use_gpu, registry, base_image
        )
        print(f"✅ 镜像构建成功: {image_name}")
        print("🌍 地理空间支持已启用 (rasterio/GDAL)")
        if use_gpu:
            print("🔥 GPU支持已启用")

        # 推送镜像
        manager = DockerManager()
        if manager.push_image(image_name):
            print("✅ 镜像推送成功!")
            print(f"\n🎉 部署完成! 镜像: {image_name}")
        else:
            print("❌ 镜像推送失败!")
            sys.exit(1)

    except Exception as e:
        error_msg = str(e)
        if "Cannot connect to the Docker daemon" in error_msg:
            print("❌ 无法连接Docker服务")
            print("💡 请确保Docker已启动并可访问")
        elif any(
            keyword in error_msg.lower()
            for keyword in [
                "tls: bad record mac",
                "manifest unknown",
                "connection reset",
                "timeout",
                "registry-1.docker.io",
            ]
        ):
            print("❌ 网络连接问题导致部署失败")
            print("💡 详细的解决方案请查看上方输出")
        else:
            print(f"❌ 部署失败: {e}")
        sys.exit(1)


def main():
    """主入口点"""
    parser = argparse.ArgumentParser(
        prog="inoyb",
        description="inoyb - 基于mc.json配置的Gradio模型服务框架\n"
        "支持Docker镜像构建、推送和管理功能",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  inoyb check                    # 检查项目结构
  inoyb serve                    # 本地运行服务
  inoyb serve --dev --open       # 开发模式，自动打开浏览器
  inoyb build                    # 构建Docker镜像 (CPU版本，包含rasterio/GDAL)
  inoyb build --gpu              # 构建GPU版本镜像 (包含rasterio/GDAL+CUDA)
  inoyb run <镜像名>             # 运行Docker镜像
  
  # 镜像源配置
  inoyb build --registry registry.cn-hangzhou.aliyuncs.com/library  # 使用阿里云
  inoyb build --base-image my-registry.com/python:3.12-slim         # 自定义镜像
  
  inoyb push                     # 推送最新镜像  
  inoyb deploy                   # 一键构建并推送 (CPU版本)
  inoyb deploy --gpu             # 一键构建并推送 (GPU版本)
  
  # 运行命令示例
  inoyb run inoyb/my-model:abc123                    # 基本运行
  inoyb run inoyb/my-model:abc123 --port 8080       # 指定端口
  inoyb run inoyb/my-model:abc123 --daemon          # 后台运行
  inoyb run inoyb/my-model:abc123 --env DEBUG=1     # 设置环境变量
  inoyb images list              # 查看本地镜像列表
  inoyb images list --remote     # 查看远程镜像列表
  inoyb images clean --keep 5    # 清理旧镜像
  inoyb images prune             # 清理构建缓存和无用容器
  inoyb images export <镜像名>    # 导出镜像为tar包到当前目录
  inoyb images export <镜像名> -o model.tar  # 指定输出文件名
  inoyb images export <镜像名> --path ./exports  # 导出到指定目录
  inoyb images export <镜像名> -o model.tar --path /tmp  # 完整指定
  
  # 配置管理
  inoyb config list              # 查看配置
  inoyb config set docker.host tcp://my-server:2376
  inoyb config set registry.mirror registry.cn-hangzhou.aliyuncs.com
  inoyb config set image.map.python:3.12-slim my-registry.com/python:3.12-slim

网络问题解决方案:
  # 构建失败时的常见解决方案
  
  1. 配置镜像加速 (国内用户强烈推荐)
     inoyb config set registry.mirror registry.cn-hangzhou.aliyuncs.com
     
  2. 使用阿里云镜像源
     inoyb build --registry registry.cn-hangzhou.aliyuncs.com/library
     
  3. 直接指定国内镜像
     inoyb build --base-image registry.cn-hangzhou.aliyuncs.com/library/continuumio/miniconda3:24.3.0-0
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # check命令
    check_parser = subparsers.add_parser(
        "check", help="检查项目结构", description="验证项目是否符合inoyb的构建要求"
    )
    check_parser.add_argument("--path", default=".", help="项目路径 (默认: 当前目录)")
    check_parser.set_defaults(func=cmd_check)

    # serve命令
    serve_parser = subparsers.add_parser(
        "serve", help="本地运行服务", description="在本地启动gogogo.py服务"
    )
    serve_parser.add_argument("--path", default=".", help="项目路径 (默认: 当前目录)")
    serve_parser.add_argument(
        "--port", type=int, default=7860, help="服务端口 (默认: 7860)"
    )
    serve_parser.add_argument(
        "--host", default="0.0.0.0", help="绑定主机 (默认: 0.0.0.0)"
    )
    serve_parser.add_argument("--reload", action="store_true", help="文件变更自动重载")
    serve_parser.add_argument(
        "--dev", action="store_true", help="开发模式 (等同--reload)"
    )
    serve_parser.add_argument("--open", action="store_true", help="启动后打开浏览器")
    serve_parser.add_argument("--verbose", action="store_true", help="详细日志输出")
    serve_parser.set_defaults(func=cmd_serve)

    # run命令
    run_parser = subparsers.add_parser(
        "run", help="运行Docker镜像", description="启动Docker镜像容器"
    )
    run_parser.add_argument("image", help="Docker镜像名 (如: inoyb/my-model:abc123)")
    run_parser.add_argument(
        "--port", type=int, default=7860, help="端口映射 (默认: 7860)"
    )
    run_parser.add_argument("-d", "--daemon", action="store_true", help="后台运行")
    run_parser.add_argument(
        "--rm", action="store_true", default=True, help="容器退出后自动删除"
    )
    run_parser.add_argument(
        "-it", "--interactive", action="store_true", help="交互模式"
    )
    run_parser.add_argument("--name", help="容器名称")
    run_parser.add_argument("--env", action="append", help="环境变量 (格式: KEY=VALUE)")
    run_parser.add_argument(
        "--volume", action="append", help="卷挂载 (格式: host_path:container_path)"
    )
    run_parser.set_defaults(func=cmd_run)

    # build命令
    build_parser = subparsers.add_parser(
        "build",
        help="构建Docker镜像",
        description="从项目源码构建Docker镜像。需要gogogo.py, mc.json, requirements.txt和model/目录",
    )
    build_parser.add_argument("--path", default=".", help="项目路径 (默认: 当前目录)")
    build_parser.add_argument("--gpu", action="store_true", help="启用GPU支持")
    build_parser.add_argument(
        "--registry",
        help="镜像仓库前缀 (如: registry.cn-hangzhou.aliyuncs.com/library)",
    )
    build_parser.add_argument(
        "--base-image", help="完整的基础镜像名 (如: my-registry.com/python:3.12-slim)"
    )
    build_parser.set_defaults(func=cmd_build)

    # push命令
    push_parser = subparsers.add_parser(
        "push", help="推送Docker镜像", description="推送镜像到远程Docker服务器"
    )
    push_parser.add_argument("--image", help="指定镜像名称 (默认: 最新镜像)")
    push_parser.set_defaults(func=cmd_push)

    # images命令
    images_parser = subparsers.add_parser("images", help="管理镜像")
    images_subparsers = images_parser.add_subparsers(dest="action", help="镜像操作")

    # images list
    list_parser = images_subparsers.add_parser("list", help="列出镜像")
    list_parser.add_argument(
        "--remote", action="store_true", help="显示远程镜像而不是本地镜像"
    )

    # images clean
    clean_parser = images_subparsers.add_parser("clean", help="清理旧镜像")
    clean_parser.add_argument("--keep", type=int, help="保留镜像数量 (默认: 3)")

    # images rm
    rm_parser = images_subparsers.add_parser("rm", help="删除镜像")
    rm_parser.add_argument("name", help="镜像名称")

    # images prune
    images_subparsers.add_parser("prune", help="清理构建缓存和无用容器")

    # images export
    export_parser = images_subparsers.add_parser("export", help="导出镜像为tar包")
    export_parser.add_argument("name", help="镜像名称 (如: inoyb/my-model:abc123)")
    export_parser.add_argument("-o", "--output", help="输出文件名 (默认: 自动生成)")
    export_parser.add_argument("--path", help="导出目录路径 (默认: 当前目录)")

    images_parser.set_defaults(func=cmd_images)

    # config命令
    config_parser = subparsers.add_parser("config", help="配置管理")
    config_subparsers = config_parser.add_subparsers(dest="action", help="配置操作")

    # config set
    set_parser = config_subparsers.add_parser("set", help="设置配置")
    set_parser.add_argument("key", help="配置键 (如: docker.host 或 default)")
    set_parser.add_argument("value", nargs="?", help="配置值")

    # config list
    config_subparsers.add_parser("list", help="列出配置")

    config_parser.set_defaults(func=cmd_config)

    # deploy命令
    deploy_parser = subparsers.add_parser(
        "deploy",
        help="一键构建并推送",
        description="构建Docker镜像并推送到远程服务器的组合命令",
    )
    deploy_parser.add_argument("--path", default=".", help="项目路径 (默认: 当前目录)")
    deploy_parser.add_argument("--gpu", action="store_true", help="启用GPU支持")
    deploy_parser.add_argument(
        "--registry",
        help="镜像仓库前缀 (如: registry.cn-hangzhou.aliyuncs.com/library)",
    )
    deploy_parser.add_argument(
        "--base-image", help="完整的基础镜像名 (如: my-registry.com/python:3.12-slim)"
    )
    deploy_parser.set_defaults(func=cmd_deploy)

    # 解析参数
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # 执行对应命令
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
