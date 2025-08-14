import importlib
import inspect
import logging
from pathlib import Path


def normalize_module_path(path: str) -> str:
    r"""
    将文件系统路径转换为Python模块路径

    :param path: 文件系统路径（可能包含 / 或 \）
    :return: Python模块路径（使用点分隔）
    """
    # 使用Path对象来规范化路径，然后转换为模块路径
    path_obj = Path(path)
    # 将路径分隔符统一替换为点
    parts = []
    for part in path_obj.parts:
        # 跳过相对路径标记
        if part not in ('.', '..'):
            parts.append(part)
    return '.'.join(parts)


def import_all_models(directory: str, recursive: bool = False, exclude_filenames: list[str] = None):
    """
    导入给定目录中的所有Python文件

    :param directory: 包含Python文件的目录的路径
    :param recursive: 是否递归导入子目录
    :param exclude_filenames: 要排除的文件名
    """
    if exclude_filenames is None:
        exclude_filenames = []

    # 规范化目录路径
    directory_path = Path(directory)

    # 确保目录存在
    if not directory_path.exists():
        raise ValueError(f'Directory {directory} does not exist')

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
            # 将文件系统路径转换为模块路径
            module_base = normalize_module_path(directory)
            module_path = f'{module_base}.{module_name}'

            try:
                importlib.import_module(module_path)
            except ImportError as e:
                logging.error(f'Failed to import {module_path}: {e}')
                raise


def execute_function_in_all_modules(directory: str, function_name: str, *args, **kwargs):
    """
    在给定目录中的所有Python文件中执行指定的函数

    :param directory: 包含Python文件的目录的路径
    :param function_name: 要执行的函数的名称
    :param *args: 传递给函数的参数
    :param **kwargs: 传递给函数的关键字参数
    """
    # 规范化目录路径
    directory_path = Path(directory)

    # 确保目录存在
    if not directory_path.exists():
        raise ValueError(f'Directory {directory} does not exist')

    for entry in directory_path.iterdir():
        if entry.is_file() and entry.name != '__init__.py' and entry.suffix == '.py':
            module_name = entry.stem
            module_base = normalize_module_path(directory)
            module_path = f'{module_base}.{module_name}'

            try:
                module = importlib.import_module(module_path)
                if hasattr(module, function_name):
                    func = getattr(module, function_name)
                    func(*args, **kwargs)
            except ImportError as e:
                logging.error(f'Failed to import {module_path}: {e}')


def get_attributes_from_all_modules(directory: str, attribute_name: str):
    """
    从给定目录中的所有Python文件中获取指定的属性（函数或变量）

    :param directory: 包含Python文件的目录的路径
    :param attribute_name: 要获取的属性的名称
    :return: 字典，其中的键是模块的路径，值是模块的属性
    """
    attributes = {}
    # 规范化目录路径
    directory_path = Path(directory)

    # 确保目录存在
    if not directory_path.exists():
        raise ValueError(f'Directory {directory} does not exist')

    for entry in directory_path.iterdir():
        if entry.is_file() and entry.name != '__init__.py' and entry.suffix == '.py':
            module_name = entry.stem
            module_base = normalize_module_path(directory)
            module_path = f'{module_base}.{module_name}'

            try:
                module = importlib.import_module(module_path)
                if hasattr(module, attribute_name):
                    attributes[module_path] = getattr(module, attribute_name)
            except ImportError as e:
                logging.error(f'Failed to import {module_path}: {e}')

    return attributes


def get_classes_inheriting_from_base(
    directory: str, base_class: type, exclude_file_name: list[str] = None, include_base_class: bool = False
) -> dict[str, dict[str, type]]:
    """
    从给定目录中的所有Python文件中获取继承特定基类的类

    :param directory: 包含Python文件的目录路径
    :param base_class: 要匹配的基类
    :param exclude_file_name: 要排除的文件名
    :param include_base_class: 是否包括基类
    :return: 字典，其中键是模块路径，值是继承指定基类的类的字典
    """
    if exclude_file_name is None:
        exclude_file_name = []

    class_dict = {}
    # 规范化目录路径
    directory_path = Path(directory)

    # 确保目录存在
    if not directory_path.exists():
        raise ValueError(f'Directory {directory} does not exist')

    for entry in directory_path.iterdir():
        if entry.is_file() and entry.name != '__init__.py' and entry.suffix == '.py':
            if entry.name in exclude_file_name:
                continue

            module_name = entry.stem
            module_base = normalize_module_path(directory)
            module_path = f'{module_base}.{module_name}'

            try:
                module = importlib.import_module(module_path)
            except ImportError as e:
                logging.error(f'Failed to import {module_path}: {e}')
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
                class_dict[module_path] = inheriting_classes

    return class_dict
