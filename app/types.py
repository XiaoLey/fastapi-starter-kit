#
# 公共类型定义
#
# 用于定义项目中可复用的公共类型。
#

from typing import Literal

# 用户状态
USER_STATE_TYPE = Literal['disabled', 'enabled']

# 性别
GENDER_TYPE = Literal['male', 'female', 'unknown']
