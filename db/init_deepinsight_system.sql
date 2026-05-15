CREATE DATABASE IF NOT EXISTS deepinsight_system
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE deepinsight_system;


-- =========================================================
-- 1. 数据库连接表
-- 保存用户配置的业务数据库连接信息
-- 注意：password_encrypted 存加密后的密码，不要明文存密码
-- =========================================================
CREATE TABLE IF NOT EXISTS database_connections (
  id CHAR(32) PRIMARY KEY COMMENT '连接ID，后端生成 uuid4().hex',

  alias VARCHAR(100) NOT NULL COMMENT '连接名称，如 analytics_db',
  db_type VARCHAR(50) NOT NULL COMMENT '数据库类型：mysql/postgresql/neo4j 等',

  host VARCHAR(255) NOT NULL COMMENT '数据库主机地址',
  port INT NOT NULL COMMENT '数据库端口',
  username VARCHAR(128) NOT NULL COMMENT '数据库用户名',
  password_encrypted TEXT NOT NULL COMMENT '加密后的数据库密码',
  database_name VARCHAR(128) DEFAULT NULL COMMENT '数据库名，Neo4j 等场景可为空',

  extra_config_json JSON DEFAULT NULL COMMENT '额外配置，如 charset、schema、ssl 等',

  status VARCHAR(30) NOT NULL DEFAULT 'unknown' COMMENT '连接状态：unknown/available/unavailable',
  last_test_time DATETIME DEFAULT NULL COMMENT '最后一次测试连接时间',
  last_error TEXT DEFAULT NULL COMMENT '最后一次连接失败原因',

  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

  UNIQUE KEY uk_database_connections_alias (alias),
  KEY idx_database_connections_type (db_type),
  KEY idx_database_connections_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='DeepInsight 数据库连接配置表';



-- =========================================================
-- 2. 分析任务表
-- 左侧任务列表主要查这张表
-- latest_state_json 存 LangGraph 最新状态的轻量快照，方便前端渲染当前执行情况
-- =========================================================
CREATE TABLE IF NOT EXISTS analysis_tasks (
  id CHAR(32) PRIMARY KEY COMMENT '任务ID，后端生成 uuid4().hex',

  title VARCHAR(255) NOT NULL COMMENT '任务标题，用于左侧栏展示',
  question TEXT NOT NULL COMMENT '用户原始分析需求',

  status VARCHAR(30) NOT NULL DEFAULT 'pending' COMMENT '任务状态：pending/running/succeeded/failed/cancelled',
  current_stage VARCHAR(100) DEFAULT NULL COMMENT '当前执行阶段，如 schema_read/sql_generate/report_generate',

  connection_id CHAR(32) DEFAULT NULL COMMENT '使用的数据库连接ID',

  db_alias_snapshot VARCHAR(100) DEFAULT NULL COMMENT '创建任务时的数据库连接名称快照',
  db_type_snapshot VARCHAR(50) DEFAULT NULL COMMENT '创建任务时的数据库类型快照',
  db_name_snapshot VARCHAR(128) DEFAULT NULL COMMENT '创建任务时的数据库名快照',

  scene VARCHAR(50) NOT NULL DEFAULT 'general' COMMENT '业务场景：general/ecommerce/factory/passenger_flow 等',
  report_depth VARCHAR(30) NOT NULL DEFAULT 'standard' COMMENT '报告深度：simple/standard/deep',

  latest_state_json JSON DEFAULT NULL COMMENT 'LangGraph 最新状态的轻量快照，不存超大内容',
  error_message TEXT DEFAULT NULL COMMENT '任务失败原因',

  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  started_at DATETIME DEFAULT NULL COMMENT '开始执行时间',
  finished_at DATETIME DEFAULT NULL COMMENT '结束时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

  KEY idx_analysis_tasks_status (status),
  KEY idx_analysis_tasks_created_at (created_at),
  KEY idx_analysis_tasks_updated_at (updated_at),
  KEY idx_analysis_tasks_connection_id (connection_id),

  CONSTRAINT fk_analysis_tasks_connection
    FOREIGN KEY (connection_id)
    REFERENCES database_connections(id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='DeepInsight 分析任务主表';



-- =========================================================
-- 3. 任务产物表
-- 统一管理文件类产物：CSV、图表、trace、导出的报告等
-- 现在 storage_type 可以先用 local，后面换阿里云 OSS 时改为 oss
-- =========================================================
CREATE TABLE IF NOT EXISTS task_artifacts (
  id CHAR(32) PRIMARY KEY COMMENT '产物ID，后端生成 uuid4().hex',

  task_id CHAR(32) NOT NULL COMMENT '所属任务ID',

  artifact_type VARCHAR(50) NOT NULL COMMENT '产物类型：result_csv/chart_png/trace_json/report_pdf 等',
  storage_type VARCHAR(30) NOT NULL DEFAULT 'local' COMMENT '存储类型：local/oss/s3/minio',
  uri TEXT NOT NULL COMMENT '文件地址，本地路径或 OSS URI',

  file_name VARCHAR(255) DEFAULT NULL COMMENT '文件名',
  mime_type VARCHAR(100) DEFAULT NULL COMMENT 'MIME 类型',
  size_bytes BIGINT DEFAULT NULL COMMENT '文件大小，单位字节',
  checksum VARCHAR(128) DEFAULT NULL COMMENT '文件校验值，可选',
  description TEXT DEFAULT NULL COMMENT '产物说明',

  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',

  KEY idx_task_artifacts_task_id (task_id),
  KEY idx_task_artifacts_type (artifact_type),
  KEY idx_task_artifacts_storage_type (storage_type),

  CONSTRAINT fk_task_artifacts_task
    FOREIGN KEY (task_id)
    REFERENCES analysis_tasks(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='DeepInsight 任务产物表';



-- =========================================================
-- 4. 任务步骤表
-- 展示任务执行到哪一步、每一步结果是什么
-- 注意：这张表不记录每个流式 token，只记录阶段状态和阶段最终结果
-- =========================================================
CREATE TABLE IF NOT EXISTS task_steps (
  id CHAR(32) PRIMARY KEY COMMENT '步骤ID，后端生成 uuid4().hex',

  task_id CHAR(32) NOT NULL COMMENT '所属任务ID',

  step_order INT NOT NULL COMMENT '步骤顺序',
  step_name VARCHAR(100) NOT NULL COMMENT '步骤内部名称，如 sql_generation',
  step_title VARCHAR(150) NOT NULL COMMENT '步骤展示名称，如 SQL 生成',

  status VARCHAR(30) NOT NULL DEFAULT 'pending' COMMENT '步骤状态：pending/running/succeeded/failed/skipped',

  input_summary TEXT DEFAULT NULL COMMENT '步骤输入摘要',
  output_summary TEXT DEFAULT NULL COMMENT '步骤输出摘要',
  output_json JSON DEFAULT NULL COMMENT '步骤结构化输出，小体积内容可直接存这里',

  artifact_id CHAR(32) DEFAULT NULL COMMENT '如果步骤有大体积产物，则关联 task_artifacts',

  error_message TEXT DEFAULT NULL COMMENT '步骤失败原因',

  started_at DATETIME DEFAULT NULL COMMENT '步骤开始时间',
  finished_at DATETIME DEFAULT NULL COMMENT '步骤结束时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

  UNIQUE KEY uk_task_steps_order (task_id, step_order),
  KEY idx_task_steps_task_id (task_id),
  KEY idx_task_steps_status (status),
  KEY idx_task_steps_name (step_name),
  KEY idx_task_steps_artifact_id (artifact_id),

  CONSTRAINT fk_task_steps_task
    FOREIGN KEY (task_id)
    REFERENCES analysis_tasks(id)
    ON DELETE CASCADE,

  CONSTRAINT fk_task_steps_artifact
    FOREIGN KEY (artifact_id)
    REFERENCES task_artifacts(id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='DeepInsight 任务步骤表';



-- =========================================================
-- 5. 查询结果表
-- 存 SQL、列名、前 N 行预览、总行数、完整结果文件位置
-- 完整结果不要全塞进 MySQL，放到 task_artifacts 指向的文件里
-- =========================================================
CREATE TABLE IF NOT EXISTS query_results (
  id CHAR(32) PRIMARY KEY COMMENT '查询结果ID，后端生成 uuid4().hex',

  task_id CHAR(32) NOT NULL COMMENT '所属任务ID',

  sql_text MEDIUMTEXT NOT NULL COMMENT '最终执行的 SQL',
  columns_json JSON DEFAULT NULL COMMENT '查询结果列名列表',
  preview_rows_json JSON DEFAULT NULL COMMENT '查询结果预览行，建议只存前 50 或 100 行',

  row_count BIGINT DEFAULT NULL COMMENT '完整结果总行数',
  preview_row_count INT DEFAULT NULL COMMENT '预览行数',

  result_format VARCHAR(30) DEFAULT 'csv' COMMENT '完整结果文件格式：csv/json/parquet 等',
  artifact_id CHAR(32) DEFAULT NULL COMMENT '完整查询结果文件对应的产物ID',

  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',

  KEY idx_query_results_task_id (task_id),
  KEY idx_query_results_artifact_id (artifact_id),

  CONSTRAINT fk_query_results_task
    FOREIGN KEY (task_id)
    REFERENCES analysis_tasks(id)
    ON DELETE CASCADE,

  CONSTRAINT fk_query_results_artifact
    FOREIGN KEY (artifact_id)
    REFERENCES task_artifacts(id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='DeepInsight 查询结果表';



-- =========================================================
-- 6. 报告表
-- Markdown 内容直接存 MySQL，方便前端展示
-- PDF / Word 等导出文件可以临时生成，也可以后面作为 artifact 保存
-- =========================================================
CREATE TABLE IF NOT EXISTS reports (
  id CHAR(32) PRIMARY KEY COMMENT '报告ID，后端生成 uuid4().hex',

  task_id CHAR(32) NOT NULL COMMENT '所属任务ID',

  title VARCHAR(255) NOT NULL COMMENT '报告标题',
  summary TEXT DEFAULT NULL COMMENT '报告摘要',

  markdown_content MEDIUMTEXT NOT NULL COMMENT 'Markdown 报告正文',
  html_content MEDIUMTEXT DEFAULT NULL COMMENT '可选：渲染后的 HTML 内容',

  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

  UNIQUE KEY uk_reports_task_id (task_id),

  CONSTRAINT fk_reports_task
    FOREIGN KEY (task_id)
    REFERENCES analysis_tasks(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='DeepInsight 报告表';