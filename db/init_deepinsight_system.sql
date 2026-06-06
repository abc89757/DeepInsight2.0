CREATE DATABASE IF NOT EXISTS deepinsight_system
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE deepinsight_system;


-- =========================================================
-- 1. 数据库连接表
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
-- 2. LLM 模型配置表
-- =========================================================
CREATE TABLE IF NOT EXISTS llm_models (
  id CHAR(32) PRIMARY KEY COMMENT '模型配置ID，后端生成 uuid4().hex',

  name VARCHAR(100) NOT NULL COMMENT '模型配置名称/展示名，如 qwen-plus',
  api_model_name VARCHAR(150) NOT NULL COMMENT '实际传给 API 的模型名',
  base_url VARCHAR(255) NOT NULL COMMENT '模型服务 base_url',
  api_key_encrypted TEXT NOT NULL COMMENT '加密后的 API Key',

  is_system TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否系统预置模型',
  status VARCHAR(30) NOT NULL DEFAULT 'available' COMMENT 'available/disabled',

  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

  UNIQUE KEY uk_llm_models_name (name),
  KEY idx_llm_models_status (status),
  KEY idx_llm_models_is_system (is_system)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='DeepInsight LLM 模型配置表';


-- =========================================================
-- 3. 通用任务主表
-- 所有任务类型共用：analysis / skill_distillation / skill_scene_direction / 后续更多任务
-- =========================================================
CREATE TABLE IF NOT EXISTS tasks (
  id CHAR(32) PRIMARY KEY COMMENT '任务ID，后端生成 uuid4().hex',

  task_type VARCHAR(50) NOT NULL COMMENT '任务类型：analysis/skill_distillation/skill_scene_direction 等',

  status VARCHAR(30) NOT NULL DEFAULT 'pending' COMMENT '任务状态：pending/running/succeeded/failed/cancelled',
  current_stage VARCHAR(100) DEFAULT NULL COMMENT '当前执行阶段',
  message TEXT DEFAULT NULL COMMENT '当前任务提示信息',
  error_message TEXT DEFAULT NULL COMMENT '任务失败原因',

  model_id CHAR(32) DEFAULT NULL COMMENT '本次任务使用的模型配置ID，可为空',
  model_name VARCHAR(150) DEFAULT NULL COMMENT '本次任务使用的模型名称快照，可为空',

  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  started_at DATETIME DEFAULT NULL COMMENT '开始执行时间',
  finished_at DATETIME DEFAULT NULL COMMENT '结束时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

  KEY idx_tasks_type (task_type),
  KEY idx_tasks_status (status),
  KEY idx_tasks_created_at (created_at),
  KEY idx_tasks_updated_at (updated_at),
  KEY idx_tasks_model_id (model_id),

  CONSTRAINT fk_tasks_model
    FOREIGN KEY (model_id)
    REFERENCES llm_models(id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='DeepInsight 通用任务主表';

-- =========================================================
-- 4. 分析任务扩展表
-- 只保存分析任务特有字段
-- id 同时也是 tasks.id
-- =========================================================
CREATE TABLE IF NOT EXISTS analysis_tasks (
  id CHAR(32) PRIMARY KEY COMMENT '分析任务ID，同时也是 tasks.id',

  title VARCHAR(255) NOT NULL COMMENT '分析任务标题，用于左侧栏展示',
  question TEXT NOT NULL COMMENT '用户原始分析需求',

  connection_id CHAR(32) DEFAULT NULL COMMENT '使用的数据库连接ID',

  db_alias_snapshot VARCHAR(100) DEFAULT NULL COMMENT '创建任务时的数据库连接名称快照',
  db_type_snapshot VARCHAR(50) DEFAULT NULL COMMENT '创建任务时的数据库类型快照',
  db_name_snapshot VARCHAR(128) DEFAULT NULL COMMENT '创建任务时的数据库名快照',

  scene VARCHAR(50) NOT NULL DEFAULT 'general' COMMENT '业务场景：general/ecommerce/product_sales 等',
  report_depth VARCHAR(30) NOT NULL DEFAULT 'standard' COMMENT '报告深度：simple/standard/deep',

  latest_state_json JSON DEFAULT NULL COMMENT '分析任务 LangGraph 最新状态快照，不存超大内容',

  KEY idx_analysis_tasks_connection_id (connection_id),
  KEY idx_analysis_tasks_scene (scene),

  CONSTRAINT fk_analysis_tasks_task
    FOREIGN KEY (id)
    REFERENCES tasks(id)
    ON DELETE CASCADE,

  CONSTRAINT fk_analysis_tasks_connection
    FOREIGN KEY (connection_id)
    REFERENCES database_connections(id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='DeepInsight 分析任务扩展表';

-- =========================================================
-- 5. Skill 沉淀任务扩展表
-- 同一个 task_id 下，用 skill_type 区分五类 skill 文件
-- =========================================================
CREATE TABLE IF NOT EXISTS skill_distillation_tasks (
  task_id CHAR(32) NOT NULL COMMENT '所属沉淀任务ID，对应 tasks.id',

  skill_type VARCHAR(50) NOT NULL COMMENT 'Skill 文件类型：SKILL/metrics/calculations/analysis/report_template',
  source_analysis_task_id CHAR(32) NOT NULL COMMENT '来源分析任务ID，对应 analysis_tasks.id',

  target_skill_name VARCHAR(100) DEFAULT NULL COMMENT '最终沉淀出的场景 skill 名称，如 product_sales',
  target_skill_display_name VARCHAR(150) DEFAULT NULL COMMENT '场景展示名称，如 商品销售分析',

  candidate_dir TEXT DEFAULT NULL COMMENT '候选 skill 临时目录',
  candidate_file_path TEXT DEFAULT NULL COMMENT '当前 skill_type 候选文件路径',
  final_file_path TEXT DEFAULT NULL COMMENT '审核通过后写入正式 skill 目录的文件路径',

  max_rounds INT NOT NULL DEFAULT 3 COMMENT '最大迭代轮次',
  completed_rounds INT NOT NULL DEFAULT 0 COMMENT '已完成迭代轮次',
  final_score DECIMAL(5,2) DEFAULT NULL COMMENT '最终审核分数',
  evaluator_decision VARCHAR(30) DEFAULT NULL COMMENT '审核结果：accept/revise/reject/max_rounds_reached',

  context_json JSON DEFAULT NULL COMMENT '本 skill_type 使用的裁剪上下文',
  latest_state_json JSON DEFAULT NULL COMMENT '沉淀子任务最新 graph state 快照',
  mining_result_json JSON DEFAULT NULL COMMENT 'SceneMiner 输出结果',
  generated_content MEDIUMTEXT DEFAULT NULL COMMENT '生成的 Markdown 内容',
  evaluation_json JSON DEFAULT NULL COMMENT '最后一轮审核结果',

  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  started_at DATETIME DEFAULT NULL COMMENT '开始执行时间',
  finished_at DATETIME DEFAULT NULL COMMENT '结束时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

  PRIMARY KEY (task_id, skill_type),

  KEY idx_skill_distillation_source_task (source_analysis_task_id),
  KEY idx_skill_distillation_skill_name (target_skill_name),
  KEY idx_skill_distillation_decision (evaluator_decision),

  CONSTRAINT fk_skill_distillation_task
    FOREIGN KEY (task_id)
    REFERENCES tasks(id)
    ON DELETE CASCADE,

  CONSTRAINT fk_skill_distillation_source_analysis
    FOREIGN KEY (source_analysis_task_id)
    REFERENCES analysis_tasks(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='DeepInsight Skill 沉淀任务扩展表';

-- =========================================================
-- 6. Skill 场景定性任务扩展表
-- 每次 Skill 沉淀任务开始前，先创建一个独立定性任务
-- =========================================================
CREATE TABLE IF NOT EXISTS skill_scene_direction_tasks (
  task_id CHAR(32) PRIMARY KEY COMMENT '场景定性任务ID，对应 tasks.id',

  distillation_task_id CHAR(32) NOT NULL COMMENT '所属 Skill 沉淀任务ID，对应 tasks.id',
  source_analysis_task_id CHAR(32) NOT NULL COMMENT '来源分析任务ID，对应 analysis_tasks.id',

  max_debate_rounds INT NOT NULL DEFAULT 3 COMMENT '最大辩论轮数',
  completed_debate_rounds INT NOT NULL DEFAULT 0 COMMENT '已完成辩论轮数',

  judge_decision VARCHAR(30) DEFAULT NULL COMMENT '裁判最终判断：收敛/不收敛',
  selected_debater_id VARCHAR(50) DEFAULT NULL COMMENT '最终随机选中的选手ID',

  context_json JSON DEFAULT NULL COMMENT '场景定性使用的裁剪上下文',
  latest_state_json JSON DEFAULT NULL COMMENT '场景定性 graph 最新 state 快照',
  scene_direction MEDIUMTEXT DEFAULT NULL COMMENT '最终场景方向自然语言描述',

  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  started_at DATETIME DEFAULT NULL COMMENT '开始执行时间',
  finished_at DATETIME DEFAULT NULL COMMENT '结束时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

  KEY idx_scene_direction_distillation_task (distillation_task_id),
  KEY idx_scene_direction_source_task (source_analysis_task_id),
  KEY idx_scene_direction_judge_decision (judge_decision),

  CONSTRAINT fk_scene_direction_task
    FOREIGN KEY (task_id)
    REFERENCES tasks(id)
    ON DELETE CASCADE,

  CONSTRAINT fk_scene_direction_distillation_task
    FOREIGN KEY (distillation_task_id)
    REFERENCES tasks(id)
    ON DELETE CASCADE,

  CONSTRAINT fk_scene_direction_source_analysis
    FOREIGN KEY (source_analysis_task_id)
    REFERENCES analysis_tasks(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='DeepInsight Skill 场景定性任务扩展表';

-- =========================================================
-- 7. 任务产物表
-- =========================================================
CREATE TABLE IF NOT EXISTS task_artifacts (
  id CHAR(32) PRIMARY KEY COMMENT '产物ID，后端生成 uuid4().hex',

  task_id CHAR(32) NOT NULL COMMENT '所属任务ID，对应 tasks.id',

  artifact_type VARCHAR(50) NOT NULL COMMENT '产物类型：result_csv/chart_png/trace_json/report_pdf/skill_md 等',
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
    REFERENCES tasks(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='DeepInsight 任务产物表';


-- =========================================================
-- 8. 任务步骤表
-- =========================================================
CREATE TABLE IF NOT EXISTS task_steps (
  id CHAR(32) PRIMARY KEY COMMENT '步骤ID，后端生成 uuid4().hex',

  task_id CHAR(32) NOT NULL COMMENT '所属任务ID，对应 tasks.id',

  step_order INT NOT NULL COMMENT '步骤顺序',
  step_name VARCHAR(100) NOT NULL COMMENT '步骤内部名称',
  step_title VARCHAR(150) NOT NULL COMMENT '步骤展示名称',

  status VARCHAR(30) NOT NULL DEFAULT 'pending' COMMENT '步骤状态：pending/running/succeeded/failed/skipped',

  input_summary TEXT DEFAULT NULL COMMENT '步骤输入摘要',
  output_summary TEXT DEFAULT NULL COMMENT '步骤输出摘要',
  output_json JSON DEFAULT NULL COMMENT '步骤结构化输出',

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
    REFERENCES tasks(id)
    ON DELETE CASCADE,

  CONSTRAINT fk_task_steps_artifact
    FOREIGN KEY (artifact_id)
    REFERENCES task_artifacts(id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='DeepInsight 任务步骤表';


-- =========================================================
-- 9. 查询结果表
-- =========================================================
CREATE TABLE IF NOT EXISTS query_results (
  id CHAR(32) PRIMARY KEY COMMENT '查询结果ID，后端生成 uuid4().hex',

  task_id CHAR(32) NOT NULL COMMENT '所属任务ID，对应 tasks.id',

  sql_text MEDIUMTEXT NOT NULL COMMENT '最终执行的 SQL',
  columns_json JSON DEFAULT NULL COMMENT '查询结果列名列表',
  preview_rows_json JSON DEFAULT NULL COMMENT '查询结果预览行',

  row_count BIGINT DEFAULT NULL COMMENT '完整结果总行数',
  preview_row_count INT DEFAULT NULL COMMENT '预览行数',

  result_format VARCHAR(30) DEFAULT 'csv' COMMENT '完整结果文件格式：csv/json/parquet 等',
  artifact_id CHAR(32) DEFAULT NULL COMMENT '完整查询结果文件对应的产物ID',

  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',

  KEY idx_query_results_task_id (task_id),
  KEY idx_query_results_artifact_id (artifact_id),

  CONSTRAINT fk_query_results_task
    FOREIGN KEY (task_id)
    REFERENCES tasks(id)
    ON DELETE CASCADE,

  CONSTRAINT fk_query_results_artifact
    FOREIGN KEY (artifact_id)
    REFERENCES task_artifacts(id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='DeepInsight 查询结果表';


-- =========================================================
-- 10. 报告表
-- =========================================================
CREATE TABLE IF NOT EXISTS reports (
  id CHAR(32) PRIMARY KEY COMMENT '报告ID，后端生成 uuid4().hex',

  task_id CHAR(32) NOT NULL COMMENT '所属任务ID，对应 tasks.id',

  title VARCHAR(255) NOT NULL COMMENT '报告标题',
  summary TEXT DEFAULT NULL COMMENT '报告摘要',

  markdown_content MEDIUMTEXT NOT NULL COMMENT 'Markdown 报告正文',
  html_content MEDIUMTEXT DEFAULT NULL COMMENT '可选：渲染后的 HTML 内容',

  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

  UNIQUE KEY uk_reports_task_id (task_id),

  CONSTRAINT fk_reports_task
    FOREIGN KEY (task_id)
    REFERENCES tasks(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='DeepInsight 报告表';
