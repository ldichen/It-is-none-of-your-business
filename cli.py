"""
inoyb命令行工具
"""

import sys
import argparse
from pathlib import Path
from typing import Optional
from .docker.builder import DockerBuilder
from .docker.manager import DockerManager
from .docker.config import DockerConfig
from .utils.logger import get_logger

logger = get_logger(__name__)


def cmd_build(args):
    """构建Docker镜像"""
    use_gpu = getattr(args, 'gpu', False)
    
    version_desc = "GPU版本" if use_gpu else "CPU版本"
    print(f"🚀 开始构建Docker镜像 ({version_desc})...")

    try:
        # 检查Docker连接
        print("🔍 检查Docker环境...")
        builder = DockerBuilder()

        image_name, image_id = builder.build_image(args.path, use_gpu)

        print(f"\n🎉 镜像构建成功!")
        print(f"   📦 镜像名称: {image_name}")
        print(f"   🆔 镜像ID: {image_id[:12]}")
        print(f"   🌍 地理空间支持: 已启用 (GDAL/PROJ/GEOS)")
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
            # 列出本地镜像
            print("📦 本地镜像:")
            images = builder.list_local_images()
            if not images:
                print("   (没有找到镜像)")
            else:
                for img in images:
                    size_mb = img["size"] / 1024 / 1024
                    print(f"   {img['name']} ({img['id']}) - {size_mb:.1f}MB")

            # 列出远程镜像（如果可用）
            print("\n☁️  远程镜像:")
            try:
                remote_images = manager.list_remote_images()
                if not remote_images:
                    print("   (没有找到镜像或无法连接)")
                else:
                    for img in remote_images:
                        size_mb = img["size"] / 1024 / 1024 if img["size"] else 0
                        print(f"   {img['name']} ({img['id']}) - {size_mb:.1f}MB")
            except:
                print("   (无法连接到远程服务器)")

        elif args.action == "clean":
            keep_count = args.keep or 3
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
            else:
                print(f"❌ 未知配置项: {args.key}")
                print("💡 支持的配置项:")
                print("   - default: 切换回默认服务器")
                print("   - docker.host <地址>: 设置Docker服务器地址")
                sys.exit(1)

        elif args.action == "list":
            print("📋 当前配置:")
            print(f"   Docker服务器: {config.get_docker_host()}")
            print(
                f"   使用默认服务器: {'是' if config.is_using_default_server() else '否'}"
            )
            print(f"   镜像仓库: {config.get_registry()}")
            print("   模板支持:")
            print("     - CPU版本 (默认) - 包含 GDAL/PROJ/GEOS")
            print("     - GPU版本 (--gpu) - 包含 GDAL/PROJ/GEOS + CUDA")

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


def cmd_deploy(args):
    """一键构建并推送"""
    try:
        use_gpu = getattr(args, 'gpu', False)
        
        version_desc = "GPU版本" if use_gpu else "CPU版本"
        print(f"🚀 开始部署流程 ({version_desc})...")

        # 构建镜像
        builder = DockerBuilder()
        image_name, _image_id = builder.build_image(args.path, use_gpu)
        print(f"✅ 镜像构建成功: {image_name}")
        print("🌍 地理空间支持已启用")
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
  inoyb build                    # 构建Docker镜像 (CPU版本，包含GDAL)
  inoyb build --gpu              # 构建GPU版本镜像 (包含GDAL+CUDA)
  inoyb push                     # 推送最新镜像  
  inoyb deploy                   # 一键构建并推送 (CPU版本)
  inoyb deploy --gpu             # 一键构建并推送 (GPU版本)
  inoyb images list              # 查看镜像列表
  inoyb images clean --keep 5    # 清理旧镜像
  inoyb config list              # 查看配置
  inoyb config set docker.host tcp://my-server:2376
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # check命令
    check_parser = subparsers.add_parser(
        "check", help="检查项目结构", description="验证项目是否符合inoyb的构建要求"
    )
    check_parser.add_argument("--path", default=".", help="项目路径 (默认: 当前目录)")
    check_parser.set_defaults(func=cmd_check)

    # build命令
    build_parser = subparsers.add_parser(
        "build",
        help="构建Docker镜像",
        description="从项目源码构建Docker镜像。需要gogogo.py, mc.json, requirements.txt和model/目录",
    )
    build_parser.add_argument("--path", default=".", help="项目路径 (默认: 当前目录)")
    build_parser.add_argument("--gpu", action="store_true", help="启用GPU支持")
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

    # images clean
    clean_parser = images_subparsers.add_parser("clean", help="清理旧镜像")
    clean_parser.add_argument("--keep", type=int, help="保留镜像数量 (默认: 3)")

    # images rm
    rm_parser = images_subparsers.add_parser("rm", help="删除镜像")
    rm_parser.add_argument("name", help="镜像名称")

    images_parser.set_defaults(func=cmd_images)

    # config命令
    config_parser = subparsers.add_parser("config", help="配置管理")
    config_subparsers = config_parser.add_subparsers(dest="action", help="配置操作")

    # config set
    set_parser = config_subparsers.add_parser("set", help="设置配置")
    set_parser.add_argument("key", help="配置键 (如: docker.host 或 default)")
    set_parser.add_argument("value", nargs="?", help="配置值")

    # config list
    list_config_parser = config_subparsers.add_parser("list", help="列出配置")

    config_parser.set_defaults(func=cmd_config)

    # deploy命令
    deploy_parser = subparsers.add_parser(
        "deploy",
        help="一键构建并推送",
        description="构建Docker镜像并推送到远程服务器的组合命令",
    )
    deploy_parser.add_argument("--path", default=".", help="项目路径 (默认: 当前目录)")
    deploy_parser.add_argument("--gpu", action="store_true", help="启用GPU支持")
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
