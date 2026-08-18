# AI Benefit Desk V0.1

个人 AI 福利监控系统的本地长期数据层与真理层（Source of Truth），与 ChatGPT Web Research 配合使用。

---

## 📖 核心职责分工

- **ChatGPT 负责**：
  - 外部 Web 搜索与深度调查
  - 官方第一方证据寻找（S / A 级）
  - 状态判断、去重建议、线索聚类与漏检复盘
  - 按《AI Benefit Data Exchange Protocol V0.1》生成标准 `AI-Benefit-Scan-Import.json`
- **AI Benefit Desk 负责**：
  - 本地长期持久化与真理层（Source of Truth）
  - 永久唯一 ID 分配（`BEN-xxxxxx`, `LEAD-xxxxxx`, `SRC-xxxxxx`, `COV-xxxxxx`, `MCHK-xxxxxx`, `SCAN-YYYYMMDD-xxx`）
  - 扫描上下文裁剪导出（`AI-Benefit-Scan-Context.json`）
  - 严格门禁校验（Protocol/Schema、基线版本、幂等性、Evidence Gate、Coverage Gate、REVIEW_NOT_DUE、CREATE去重）
  - 单事务原子写入与全量审计（`import_audits`）
  - 物理隔离用户个人操作状态（`user_benefit_states`，导入绝不覆盖）
  - 全中文用户界面与行动看板

---

## 🏛️ 规约依据 (Canonical Sources)

本项目严格遵循以下 5 个正式规约：
1. `AI-福利监控规则-V1.2.1` (V1.2.1)
2. `Vendor-Pool-V1.2` (V1.2 Final)
3. `Search-Playbook-V1.2.1` (V1.2.1 Final)
4. `AI-Benefit-Schema-V1.2.1` (V1.2.1 Final)
5. `AI-Benefit-Data-Exchange-Protocol-V0.1` (V0.1)

---

## 🚀 快速启动

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 运行应用
```bash
streamlit run app.py
```
启动后在浏览器打开本地服务（默认 `http://localhost:8501`）。

### 3. 运行自动化测试
```bash
pytest tests/ -v
```

---

## 📁 项目结构

```text
AI_Benefit_Randar/
├── app.py                      # Streamlit 主入口
├── pages/                      # 8 大纯中文页面
│   ├── 01_总览.py               # 首页关键行动指标与待办
│   ├── 02_福利库.py             # 已确认福利列表、多维筛选与个人状态维护
│   ├── 03_线索队列.py           # 未充分验证线索管理与升级/驳回
│   ├── 04_覆盖记录.py           # 最新覆盖矩阵与完整历史事件流
│   ├── 05_官方入口库.py         # Canonical Sources 官方入口管理
│   ├── 06_建议人工检查.py       # 盲区核查任务与结果录入
│   ├── 07_扫描结果导入.py       # JSON 上传、门禁校验、中文预览与单事务入库
│   └── 08_扫描上下文导出.py     # 规范上下文裁剪导出与文件下载
├── ai_benefit_desk/
│   ├── config.py               # 基础配置与版本常量
│   ├── db/
│   │   ├── database.py         # SQLite 数据库引擎与 Session 工厂
│   │   ├── models.py           # SQLAlchemy 9 张表的 ORM 模型
│   │   └── init_db.py          # 数据库初始化与初始基线种子
│   ├── schemas/
│   │   ├── benefit_models.py   # Benefit Schema V1.2.1 Pydantic 校验模型
│   │   └── protocol_models.py  # Protocol V0.1 导入/导出 Pydantic 模型
│   ├── services/
│   │   ├── id_service.py       # 永久 ID 生成与 local_ref 事务映射
│   │   ├── validation_service.py # 协议/Schema/Evidence/Coverage 门禁校验器
│   │   ├── dedup_service.py    # CREATE 疑似重复检测服务
│   │   ├── review_service.py   # 到期复查与指标统计服务
│   │   ├── export_service.py   # 上下文裁剪与导出服务
│   │   └── import_service.py   # 导入编排、预览与事务写入
│   └── utils/
│       ├── enum_labels.py      # 英文内部枚举 -> 中文展示映射
│       ├── date_utils.py       # 日期格式化与到期判定
│       └── json_utils.py       # JSON 序列化工具
├── tests/
│   ├── conftest.py             # 测试夹具 (内存 SQLite)
│   └── test_benefit_desk.py    # TEST-001 ~ TEST-017 全量单测
├── data/
│   └── benefit_desk.db         # 本地 SQLite 数据文件
├── README.md                   # 项目说明
└── requirements.txt            # 项目依赖
```

---

## 🧪 自动化测试验证 (TEST-001 ~ TEST-017)

- `TEST-001`: 首次 EMPTY Context 可以正常导出
- `TEST-002`: CREATE Benefit 入库后生成永久 benefit_id
- `TEST-003`: UPDATE 不存在 benefit_id → FAIL
- `TEST-004`: 相同 scan_id 二次导入 → 被阻止 (幂等性)
- `TEST-005`: baseline_revision 冲突 → 被发现并阻断
- `TEST-006`: REVIEW_NOT_DUE 不刷新 actual_checked_at
- `TEST-007`: DEEP_FULL_SCAN Import 中 REVIEW_NOT_DUE → FAIL
- `TEST-008`: CONFIRM_NO_CHANGE 必须引用合法已存在 benefit_id
- `TEST-009`: CONFIRMED 没有 S/A Evidence → Evidence Gate 警告与阻断
- `TEST-010`: Lead 可以 resolve 到同一 Import 中的新 Benefit (`local_ref`)
- `TEST-011`: Lead 可以 resolve 到已有 Benefit (`benefit_id`)
- `TEST-012`: Source DEPRECATE 不物理删除历史
- `TEST-013`: Scan Import 绝不修改用户个人操作状态 (`CLAIMED`)
- `TEST-014`: CREATE 疑似重复 → 进入预览，不自动创建
- `TEST-015`: 事务中途失败 → 整体原子 rollback
- `TEST-016`: 首次 Baseline 的长期既有福利不会被自动标 NEW
- `TEST-017`: 用户所有可见主要状态显示中文
