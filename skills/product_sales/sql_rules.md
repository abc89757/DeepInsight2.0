# 商品销售分析 SQL 规则

## 文档定位

本文档用于约束 `SQLEngineerNode` 生成 SQL 的方式，适用于商品销售分析场景。

本文件只写 SQL 语法、限制和常用函数，不写业务指标公式。业务指标计算规则应放在 `calculations.md` 中。

## MySQL 版本要求

- 默认使用 MySQL 8.0+ 语法。
- 可以使用 MySQL 8.0 支持的 CTE（`WITH`）和窗口函数。
- 不使用 PostgreSQL、SQL Server、Oracle 等其他数据库语法。
- 禁止使用 PostgreSQL 的 `::type`、`ILIKE`，SQL Server 的 `TOP`，Oracle 的 `ROWNUM`，以及其他非 MySQL 函数。

## 只读 SQL 约束

只允许生成：

- `SELECT`
- `WITH ... SELECT`
- 子查询
- 派生表
- `JOIN`
- `GROUP BY`
- `HAVING`
- `ORDER BY`
- `LIMIT`

禁止生成：

- `INSERT`
- `UPDATE`
- `DELETE`
- `DROP`
- `ALTER`
- `TRUNCATE`
- `CREATE`
- `REPLACE`
- `LOAD DATA`
- `SELECT ... INTO OUTFILE`
- `CALL`
- `SET`
- `GRANT`
- `REVOKE`

如需中间结果，优先使用 CTE 或派生表，不创建临时表。

## 基础查询规则

- 查询必须基于 schema 中真实存在的表、字段和连接关系。
- 不要臆造表名、字段名、外键或业务字段。
- 多表查询必须写清 `JOIN` 条件。
- 不允许无条件 `CROSS JOIN`。
- 商品销售分析优先从订单明细表出发，再关联订单表、商品表、客户表、库存表等。
- 明细查询默认加 `LIMIT 100`，除非用户明确要求完整导出。
- 排名查询必须使用 `ORDER BY` 和 `LIMIT`。

## 聚合规则

常用聚合函数：

- `SUM(x)`：求和，常用于销售额、销量、成本等累计值。
- `COUNT(*)`：统计行数。
- `COUNT(x)`：统计字段非空的行数。
- `COUNT(DISTINCT x)`：统计去重数量，如订单数、客户数。
- `AVG(x)`：求平均值，如平均价格、平均销量。
- `MIN(x)`：取最小值。
- `MAX(x)`：取最大值。

要求：

- 使用 `GROUP BY` 时，`SELECT` 中的非聚合字段必须出现在 `GROUP BY` 中。
- 默认遵守 `ONLY_FULL_GROUP_BY` 兼容写法。
- 占比、比率、均值类指标必须保留分子和分母。
- 分母可能为 0 时，使用 `NULLIF(分母, 0)` 避免除零。
- 金额结果可使用 `ROUND(x, 2)` 保留两位小数。

## 条件判断与空值处理函数

- `CASE WHEN ... THEN ... ELSE ... END`
  - 功能：多条件判断。
  - 场景：按促销/非促销分组、按订单状态分类、生成标记字段。

- `IF(condition, true_value, false_value)`
  - 功能：简单二选一判断。
  - 场景：快速生成是否促销、是否退款等字段。

- `COALESCE(a, b, c)`
  - 功能：返回第一个非 NULL 值。
  - 场景：字段补默认值，如 `COALESCE(refund_amount, 0)`。

- `IFNULL(x, default_value)`
  - 功能：如果 x 为 NULL，则返回默认值。
  - 场景：MySQL 中常用的空值补齐。

- `NULLIF(x, y)`
  - 功能：如果 x = y，则返回 NULL，否则返回 x。
  - 场景：避免除零，如 `sales / NULLIF(orders, 0)`。

## 日期时间函数

- `DATE(datetime_col)`
  - 功能：提取日期部分。
  - 注意：不要在大表 `WHERE` 条件中直接对索引时间列使用，可能导致索引失效。

- `DATE_FORMAT(datetime_col, format)`
  - 功能：按指定格式输出日期字符串。
  - 场景：按天、按月聚合展示，如 `'%Y-%m'`。

- `YEAR(datetime_col)` / `MONTH(datetime_col)` / `DAY(datetime_col)`
  - 功能：提取年、月、日。
  - 场景：按年、月、日分组统计。

- `WEEK(datetime_col)`
  - 功能：提取周序号。
  - 场景：周维度销售分析。

- `CURDATE()`
  - 功能：返回当前日期。

- `NOW()`
  - 功能：返回当前日期时间。

- `DATEDIFF(date1, date2)`
  - 功能：计算两个日期相差天数。

- `TIMESTAMPDIFF(unit, start_time, end_time)`
  - 功能：计算两个时间的差值，可按天、小时、分钟等单位。

- `DATE_ADD(date, INTERVAL n DAY)`
  - 功能：日期向后增加 n 天。

- `DATE_SUB(date, INTERVAL n DAY)`
  - 功能：日期向前减少 n 天。

时间筛选优先使用范围条件：

```sql
order_time >= '2026-05-01'
AND order_time < '2026-06-01'
```

不要优先写成：

```sql
DATE(order_time) = '2026-05-01'
```

## 窗口函数

MySQL 8.0 可使用以下窗口函数：

- `ROW_NUMBER()`
  - 功能：按排序生成连续行号。
  - 场景：每个类目取销售额 Top N 商品。

- `RANK()`
  - 功能：生成排名，相同值同名次，后续名次会跳号。
  - 场景：允许并列排名的销售榜。

- `DENSE_RANK()`
  - 功能：生成排名，相同值同名次，后续名次不跳号。
  - 场景：并列排名但希望排名连续。

- `LAG(x)`
  - 功能：取上一行的值。
  - 场景：环比、上期对比、昨日销售对比。

- `LEAD(x)`
  - 功能：取下一行的值。
  - 场景：后续周期对比。

- `SUM(x) OVER (...)`
  - 功能：窗口内求和。
  - 场景：累计销售额、分组内总额。

- `AVG(x) OVER (...)`
  - 功能：窗口内求平均。
  - 场景：移动平均、类目平均值对比。

窗口函数常用于 Top N 排名、类目内商品排名、环比/同比对比、移动平均和累计销售额。

## 字符串函数

- `TRIM(x)`：去除前后空格，常用于清洗渠道名、商品名、地区名。
- `LOWER(x)` / `UPPER(x)`：转换大小写，常用于统一英文渠道、品牌、地区字段。
- `CONCAT(a, b, ...)`：拼接字符串，常用于拼接展示字段。
- `SUBSTRING(x, start, len)`：截取字符串，常用于截取编码、日期字符串等。
- `LEFT(x, n)` / `RIGHT(x, n)`：取左侧或右侧 n 个字符，常用于处理编号、地区码、月份字段。
- `REPLACE(x, old, new)`：替换字符串内容，常用于标准化字段值。
- `LENGTH(x)`：返回字节长度。
- `CHAR_LENGTH(x)`：返回字符长度，更适合中文字段。

注意：不要在大表 `WHERE` 条件中频繁对索引列使用字符串函数。

## 数值函数

- `ROUND(x, n)`：四舍五入保留 n 位小数，常用于金额、比率、客单价展示。
- `FLOOR(x)`：向下取整。
- `CEIL(x)`：向上取整。
- `ABS(x)`：取绝对值，常用于计算差值幅度。
- `GREATEST(a, b, ...)`：取多个值中的最大值，常用于边界保护。
- `LEAST(a, b, ...)`：取多个值中的最小值，常用于限制比率或阈值范围。

## JOIN 规则

- 默认优先使用 `INNER JOIN` 和 `LEFT JOIN`。
- 保留主事实表全部记录时使用 `LEFT JOIN`。
- 只需要匹配成功记录时使用 `INNER JOIN`。
- MySQL 不支持原生 `FULL OUTER JOIN`，不要生成。
- JOIN 前必须确认连接键，例如 `order_id`、`sku_id`、`customer_id`、`store_id`、`channel_id`。
- JOIN 后如果行数异常变大，应优先检查连接键是否导致一对多膨胀。

## 性能与安全规则

- 查询大表必须有时间范围或明确过滤条件。
- 不要 `SELECT *`，只选择需要字段。
- 排序、分组、连接字段应优先使用索引字段。
- 对大结果集使用 `LIMIT`。
- 避免多层深度嵌套 SQL。
- 避免在大表中使用 `ORDER BY RAND()`。
- 生成 SQL 时不要拼接用户输入，应由执行层做参数绑定。
- 无法确认口径时，应返回“需要补充字段或口径”，不要强行生成。
