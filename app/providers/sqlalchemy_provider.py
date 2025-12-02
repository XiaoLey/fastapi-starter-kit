import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria
from sqlalchemy.orm.session import ORMExecuteState
from sqlalchemy.orm.util import AliasedClass


# @event.listens_for(Session, 'do_orm_execute')
# def add_soft_delete_filter(execute_state: ORMExecuteState):
#     """
#     添加软删除过滤器（判断 deleted_at 字段）
#     注意：relationship 字段不会被过滤，需要自行处理

#     :param execute_state: 执行状态
#     """
#     if (
#         execute_state.is_select
#         and not execute_state.is_column_load
#         and not execute_state.is_relationship_load  # 排除 relationship
#     ):
#         # 使用一个集合来存储已经处理的模型类或别名的原始模型
#         processed_entities = set()

#         # 遍历查询中的每个 entity
#         for entity in execute_state.statement.column_descriptions:
#             entity_class = entity.get('entity', None)

#             # 检查是否存在实体并且是否具有软删除字段
#             if entity_class and hasattr(entity_class, 'deleted_at'):
#                 # 获取原始模型类，处理多重别名
#                 original_class = entity_class
#                 while isinstance(original_class, AliasedClass):
#                     original_class = sa.inspect(original_class)._target

#                 # 检查该实体或其原始模型是否已经处理过
#                 if original_class not in processed_entities:
#                     # 为该实体或其原始模型添加软删除过滤器
#                     execute_state.statement = execute_state.statement.options(
#                         with_loader_criteria(
#                             original_class,
#                             lambda cls: (cls.deleted_at == None) | (cls.deleted_at > sa.func.now()),
#                             include_aliases=True,  # 处理别名的情况
#                         )
#                     )
#                     # 标记该模型或别名已处理
#                     processed_entities.add(original_class)
