# DeepInsight 前后端交互 MVP

当前版本只实现两个功能闭环：

1. 前端填写数据库连接信息，调用 FastAPI 后端测试 MySQL 连接；
2. 前端输入分析需求，调用 FastAPI 后端创建分析任务，返回 `task_id` 和初始状态。

报告展示、LangGraph 工作流、SQL 生成、SQL 审计和 SQL 执行暂时没有接入。

## 目录结构

```text
backend/
  main.py          FastAPI 后端入口
frontend/
  index.html      前端页面
  styles.css      页面样式
  script.js       前端交互逻辑
requirements.txt  后端依赖
```

## 启动后端

在项目根目录执行：

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

启动成功后访问：

```text
http://127.0.0.1:8000/api/health
```

如果返回 `DeepInsight API is running`，说明后端已经启动。

## 启动前端

可以直接双击打开：

```text
frontend/index.html
```

也可以用 VSCode 的 Live Server 打开。

## 当前接口

### 1. 健康检查

```text
GET /api/health
```

### 2. 测试数据库连接

```text
POST /api/databases/test
```

当前只真实支持 MySQL。

### 3. 创建分析任务

```text
POST /api/tasks
```

当前只创建任务，不执行真实分析。

### 4. 查询任务状态

```text
GET /api/tasks/{task_id}
```

当前任务保存在内存里，后端服务重启后会丢失。
