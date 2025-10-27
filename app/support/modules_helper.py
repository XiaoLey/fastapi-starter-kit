#
# 模块辅助工具
#
# 提供动态导入模块、执行模块中函数、获取模块属性等功能。
#

import importlib
import inspect
import logging
from pathlib import Path


def normalize_module_path(path: str) -> str:
    """将文件系统路径或模块路径统一转换为Python模块路径

    Args:
        path: 文件系统路径（'path/to/module'）或模块路径（'path.to.module'）

    Returns:
        Python模块路径（使用点分隔）
    """
    # 如果已经是点分隔的模块路径，直接返回
    if '/' not in path and '\\' not in path:
        return path

    # 否则，按照文件系统路径处理
    path_obj = Path(path)
    parts = []
    for part in path_obj.parts:
        if part not in ('.', '..'):
            parts.append(part)
    return '.'.join(parts)


def import_all_models(module_path: str, recursive: bool = False, exclude_filenames: list[str] = None):
    """导入给定模块路径中的所有Python文件

    Args:
        module_path: 模块路径（如 'app.models'）或文件系统路径（如 'app/models'）
        recursive: 是否递归导入子目录
        exclude_filenames: 要排除的文件名列表
    """
    if exclude_filenames is None:
        exclude_filenames = []

    # 规范化为模块路径
    normalized_path = normalize_module_path(module_path)

    # 转换为文件系统路径以进行目录操作
    directory_path = Path(module_path.replace('.', '/'))

    # 确保目录存在
    if not directory_path.exists():
        raise ValueError(f'Directory {directory_path} does not exist')

    # 列出当前目录中的内容
    for entry in directory_path.iterdir():
        # 如果是目录并且需要递归，就递归调用自身
        if recursive and entry.is_dir():
            import_all_models(str(entry), recursive, exclude_filenames)

        elif (
            entry.is_file()
            and entry.name not in exclude_filenames
            and entry.suffix == '.py'
            and entry.name != '__init__.py'
        ):
            # 生成模块的完整路径
            module_name = entry.stem  # 获取文件名（不含扩展名）
            full_module_path = f'{normalized_path}.{module_name}'

            try:
                importlib.import_module(full_module_path)
            except ImportError as e:
                logging.error(f'Failed to import {full_module_path}: {e}')
                raise


def execute_function_in_all_modules(module_path: str, function_name: str, *args, **kwargs):
    """在给定模块路径中的所有Python文件中执行指定的函数

    Args:
        module_path: 模块路径（如 'app.models'）或文件系统路径（如 'app/models'）
        function_name: 要执行的函数名称
        *args: 传递给函数的位置参数
        **kwargs: 传递给函数的关键字参数
    """
    # 规范化为模块路径
    normalized_path = normalize_module_path(module_path)

    # 转换为文件系统路径以进行目录操作
    directory_path = Path(module_path.replace('.', '/'))

    # 确保目录存在
    if not directory_path.exists():
        raise ValueError(f'Directory {directory_path} does not exist')

    for entry in directory_path.iterdir():
        if entry.is_file() and entry.name != '__init__.py' and entry.suffix == '.py':
            module_name = entry.stem
            full_module_path = f'{normalized_path}.{module_name}'

            try:
                module = importlib.import_module(full_module_path)
                if hasattr(module, function_name):
                    func = getattr(module, function_name)
                    func(*args, **kwargs)
            except ImportError as e:
                logging.error(f'Failed to import {full_module_path}: {e}')


def get_attributes_from_all_modules(module_path: str, attribute_name: str):
    """从给定模块路径中的所有Python文件中获取指定的属性（函数或变量）

    Args:
        module_path: 模块路径（如 'app.models'）或文件系统路径（如 'app/models'）
        attribute_name: 要获取的属性名称

    Returns:
        dict[str, Any]: 字典，键为模块路径，值为对应模块的属性
    """
    attributes = {}

    # 规范化为模块路径
    normalized_path = normalize_module_path(module_path)

    # 转换为文件系统路径以进行目录操作
    directory_path = Path(module_path.replace('.', '/'))

    # 确保目录存在
    if not directory_path.exists():
        raise ValueError(f'Directory {directory_path} does not exist')

    for entry in directory_path.iterdir():
        if entry.is_file() and entry.name != '__init__.py' and entry.suffix == '.py':
            module_name = entry.stem
            full_module_path = f'{normalized_path}.{module_name}'

            try:
                module = importlib.import_module(full_module_path)
                if hasattr(module, attribute_name):
                    attributes[full_module_path] = getattr(module, attribute_name)
            except ImportError as e:
                logging.error(f'Failed to import {full_module_path}: {e}')

    return attributes


def get_classes_inheriting_from_base(
    module_path: str, base_class: type, exclude_filenames: list[str] = None, include_base_class: bool = False
) -> dict[str, dict[str, type]]:
    """从给定模块路径中的所有Python文件中获取继承特定基类的类

    Args:
        module_path: 模块路径（如 'app.models'）或文件系统路径（如 'app/models'）
        base_class: 要匹配的基类
        exclude_filenames: 要排除的文件名列表
        include_base_class: 是否包括基类本身

    Returns:
        dict[str, dict[str, type]]: 嵌套字典，外层键为模块路径，
            内层键为类名，值为继承指定基类的类对象
    """
    if exclude_filenames is None:
        exclude_filenames = []

    class_dict = {}

    # 规范化为模块路径
    normalized_path = normalize_module_path(module_path)

    # 转换为文件系统路径以进行目录操作
    directory_path = Path(module_path.replace('.', '/'))

    # 确保目录存在
    if not directory_path.exists():
        raise ValueError(f'Directory {directory_path} does not exist')

    for entry in directory_path.iterdir():
        if entry.is_file() and entry.name != '__init__.py' and entry.suffix == '.py':
            if entry.name in exclude_filenames:
                continue

            module_name = entry.stem
            full_module_path = f'{normalized_path}.{module_name}'

            try:
                module = importlib.import_module(full_module_path)
            except ImportError as e:
                logging.error(f'Failed to import {full_module_path}: {e}')
                continue

            classes = inspect.getmembers(module, inspect.isclass)

            inheriting_classes = {}
            for name, cls in classes:
                try:
                    # 检查是否是base_class的子类
                    if issubclass(cls, base_class):
                        # 如果include_base_class为False，排除基类本身
                        if cls is not base_class or include_base_class:
                            # 排除从其他模块导入的类（只包含在当前模块定义的类）
                            if cls.__module__ == module.__name__:
                                inheriting_classes[name] = cls
                except TypeError:
                    # 可能会遇到一些不是类的对象，忽略它们
                    continue

            if inheriting_classes:
                class_dict[full_module_path] = inheriting_classes

    return class_dict
