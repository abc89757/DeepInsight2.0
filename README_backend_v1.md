# DeepInsight Backend V1

这是第一版“有 Skill 路径”的后端代码。

## 运行方式

进入本目录后：

```bash
pip install -r requirements.txt
```

配置大模型环境变量：

```bash
set DEEPINSIGHT_LLM_MODE=real
set LLM_API_KEY=你的API_KEY
set LLM_BASE_URL=https://api.deepseek.com
set LLM_MODEL=deepseek-chat
```

如果只是想先测试链路是否能跑通，可以使用 mock 模式：

```bash
set DEEPINSIGHT_LLM_MODE=mock
```

启动后端：

```bash
python main.py
```

## 接口

- GET `/api/health`
- POST `/api/databases/test`
- POST `/api/tasks`
- GET `/api/tasks/{task_id}`

## 当前流程

```text
创建任务
→ 后台启动 LangGraph
→ load_schema
→ load_skill
→ plan_query
→ generate_sql
→ audit_sql
→ execute_sql
→ analyze_data
→ generate_report
→ 前端轮询获取报告
```

## 注意

1. 当前只支持 MySQL。
2. 当前任务记录保存在内存字典中，服务重启会丢失。
3. 当前只走有 Skill 路径；`scene` 不存在时会回退到 `general` Skill。
4. `DEEPINSIGHT_LLM_MODE=mock` 只能测试链路，不会生成真实 SQL 和报告。
