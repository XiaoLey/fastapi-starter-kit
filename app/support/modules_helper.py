import importlib
import pkgutil
from collections.abc import Sequence
from types import ModuleType


def normalize_module_path(path: str) -> str:
    """接受包名或相对包路径，不依赖调用者工作目录"""
    normalized = path.replace('\\', '.').replace('/', '.')
    if not normalized or any(not part.isidentifier() for part in normalized.split('.')):
        raise ValueError('Expected a package name or relative package path')
    return normalized


def import_all_models(
    module_path: str, recursive: bool = False, exclude_filenames: Sequence[str] = ()
) -> list[ModuleType]:
    """按稳定顺序导入包内模块，任何导入失败都向调用者传播"""
    package = importlib.import_module(normalize_module_path(module_path))
    if not hasattr(package, '__path__'):
        raise ValueError('Module is not a package')

    # 以包的位置扫描，不以当前目录拼接路径
    iterator = pkgutil.walk_packages if recursive else pkgutil.iter_modules
    names = sorted(info.name for info in iterator(package.__path__, f'{package.__name__}.'))
    return [importlib.import_module(name) for name in names if f'{name.rsplit(".", 1)[-1]}.py' not in exclude_filenames]


def get_attributes_from_all_modules(
    module_path: str, attribute_name: str, *, exclude_filenames: Sequence[str] = ()
) -> dict[str, object]:
    attributes: dict[str, object] = {}
    for module in import_all_models(module_path, recursive=True, exclude_filenames=exclude_filenames):
        if attribute_name in vars(module):
            attributes[module.__name__] = vars(module)[attribute_name]
    return attributes


def execute_function_in_all_modules(module_path: str, function_name: str, *args: object, **kwargs: object) -> None:
    for function in get_attributes_from_all_modules(module_path, function_name).values():
        if not callable(function):
            raise TypeError(f'{function_name} must be callable')
        function(*args, **kwargs)


def get_classes_inheriting_from_base[T](
    module_path: str, base_class: type[T], exclude_filenames: Sequence[str] = (), include_base_class: bool = False
) -> dict[str, dict[str, type[T]]]:
    classes: dict[str, dict[str, type[T]]] = {}
    for module in import_all_models(module_path, recursive=True, exclude_filenames=exclude_filenames):
        # 只收集定义归属本模块的类，避免再次登记导入的别名
        found: dict[str, type[T]] = {}
        for name, value in vars(module).items():
            if isinstance(value, type) and issubclass(value, base_class) and value.__module__ == module.__name__:
                if include_base_class or value is not base_class:
                    found[name] = value
        if found:
            classes[module.__name__] = found
    return classes
