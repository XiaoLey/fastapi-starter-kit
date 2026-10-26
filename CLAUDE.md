<!-- agents:profile begin -->
<!-- agents:language=python modules= -->
@../.agents/python.md
<!-- agents:profile end -->

<!-- agents:project-rules begin -->
## 本项目补充

### 测试与代码结构

- 测试围绕核心用户流程和关键失败边界，不追求覆盖率，不要求逐函数、逐参数、逐分支穷举
- 优先少量真实组合/集成测试，用公开接口串起相关模块；同一契约不在多个层重复断言
- 单元测试只补关键算法或组合测试难以稳定定位的回归，不为每个辅助函数单独建立测试文件
- 不为了 mock、单点断言或测试便利新增生产模块、抽象层、配置开关或暴露内部 API；代码结构以真实职责、生命周期、协议边界和复用决定
- 不在测试替身中重写被测的 Redis/Lua、ORM 或限流算法；能使用独立真实服务就用真实服务，外部短信/邮件只保留最小发送器 fake
- 共享测试准备集中在 conftest.py，新增用例前先看能否并入现有核心流程，避免零碎文件和重复准备逻辑
- 静态检查遵循项目实际配置，只处理 warning/error，不为已关闭或降至 information/hint 的规则增加样板代码
<!-- agents:project-rules end -->
