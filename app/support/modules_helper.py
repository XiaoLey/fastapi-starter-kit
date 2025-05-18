import importlib
import inspect
import logging
import os


def import_all_models(directory: str, recursive: bool = False, exclude_filenames: list[str] = []):
    """
    导入给定目录中的所有Python文件

    :param directory: 包含Python文件的目录的路径
    :param recursive: 是否递归导入子目录
    :param exclude_filenames: 要排除的文件名
    """
    # 列出当前目录中的内容
    for entry in os.listdir(directory):
        entry_path = os.path.join(directory, entry)

        # 如果是目录并且需要递归，就递归调用自身
        if recursive and os.path.isdir(entry_path):
            import_all_models(entry_path, recursive, exclude_filenames)

        elif entry not in exclude_filenames and entry.endswith(".py") and entry != "__init__.py":
            # 生成模块的完整路径
            module_name = entry[:-3]  # 去掉文件扩展名 .py
            module_path = f"{directory.replace(os.sep, '.')}.{module_name}"
            module_path = module_path.lstrip(".")  # 去掉字符串开头的点（如果有）
            importlib.import_module(module_path)


def execute_function_in_all_modules(directory: str, function_name: str, *args, **kwargs):
    """
    在给定目录中的所有Python文件中执行指定的函数

    :param directory: 包含Python文件的目录的路径
    :param function_name: 要执行的函数的名称
    :param *args: 传递给函数的参数
    :param **kwargs: 传递给函数的关键字参数
    """
    for filename in os.listdir(directory):
        if filename != "__init__.py" and filename.endswith(".py"):
            module_name = filename[:-3]  # 去掉文件扩展名 .py
            module_path = f"{directory.replace(os.sep, '.')}.{module_name}"
            module = importlib.import_module(module_path)
            if hasattr(module, function_name):
                func = getattr(module, function_name)
                func(*args, **kwargs)


def get_attributes_from_all_modules(directory: str, attribute_name: str):
    """
    从给定目录中的所有Python文件中获取指定的属性（函数或变量）

    :param directory: 包含Python文件的目录的路径
    :param attribute_name: 要获取的属性的名称
    :return: 字典，其中的键是模块的路径，值是模块的属性
    """
    attributes = {}
    for filename in os.listdir(directory):
        if filename != "__init__.py" and filename.endswith(".py"):
            module_name = filename[:-3]  # Remove the file extension .py
            module_path = f"{directory.replace(os.sep, '.')}.{module_name}"
            module = importlib.import_module(module_path)
            if hasattr(module, attribute_name):
                attributes[module_path] = getattr(module, attribute_name)
    return attributes


def get_classes_inheriting_from_base(directory: str, base_class: type,
                                     exclude_file_name: list[str] = None,
                                     include_base_class: bool = False) -> dict[str, dict[str, type]]:
    """
    从给定目录中的所有Python文件中获取继承特定基类的类

    :param directory: 包含Python文件的目录路径
    :param base_class: 要匹配的基类
    :param exclude_file_name: 要排除的文件名
    :param include_base_class: 是否包括基类
    :return: 字典，其中键是模块路径，值是继承指定基类的类的字典
    """
    class_dict = {}
    for filename in os.listdir(directory):
        if filename != "__init__.py" and filename.endswith(".py"):
            if exclude_file_name and filename in exclude_file_name:
                continue

            module_name = filename[:-3]  # Remove the .py extension
            module_path = f"{directory.replace(os.sep, '.')}.{module_name}"

            try:
                module = importlib.import_module(module_path)
            except ImportError as e:
                logging.error(f"Failed to import {module_path}: {e}")
                continue

            classes = inspect.getmembers(module, inspect.isclass)

            inheriting_classes = {
                name: cls for name, cls in classes if issubclass(cls, base_class) and (cls is not base_class or include_base_class)
            }

            if inheriting_classes:
                class_dict[module_path] = inheriting_classes
    return class_dict
