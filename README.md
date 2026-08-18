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
1. `AI 福利监控规则 V1.2.1` (V1.2.1)
2. `Vendor Pool V1.2` (V1.2 Final)
3. `Search Playbook V1.2.2` (V1.2.2 Final)
4. `Benefit Schema V1.2.1` (V1.2.1 Final)
5. `AI Benefit Data Exchange Protocol V0.1` (V0.1)

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
│   ├── test_benefit_desk.py    # TEST-001 ~ TEST-043 全量单测
│   ├── test_compliance.py      # Golden Fixture 与 Protocol 规约合规测试
│   └── test_e2e_lifecycle.py   # 生命周期 A (初始基线) 与生命周期 B (常规全扫) 端到端测试
├── data/
│   └── benefit_desk.db         # 本地 SQLite 数据文件
├── README.md                   # 项目说明
└── requirements.txt            # 项目依赖
```

---

## 🧪 自动化测试验证 (TEST-001 ~ TEST-043 Protocol Regression & Lifecycle Tests)

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
- `TEST-018`: 未导出的未知 scan_id → FAIL
- `TEST-019`: EMPTY Baseline 要求 BUILD_INITIAL_BASELINE
- `TEST-020`: READY Baseline 拒绝 BUILD_INITIAL_BASELINE
- `TEST-021`: 非法 package_type 被严格拒绝
- `TEST-022`: 非法 Protocol 枚举值 Schema 级别阻断
- `TEST-023`: Protocol 事件时间强制要求带时区 ISO8601
- `TEST-024`: 存在 NOT_CHECKED 必然要求包含 SCAN_INCOMPLETE 且禁止 PUBLIC_COMPLETE
- `TEST-025`: Scan Context 导出包含完整 benefit_index 身份字段
- `TEST-026`: Vendor Deep Dive 正确裁剪 User Benefit State
- `TEST-027`: 同一 Import 内 local_ref 全局唯一性校验 (跨类型)
- `TEST-028`: Manual Check 引用不存在的 Benefit/Lead 校验阻断
- `TEST-029`: BenefitRecord 包含多余字段 (extra=forbid) 阻断
- `TEST-030`: scan_id 与 baseline_revision_at_export 强绑定校验
- `TEST-031`: 初始基线全生命周期测试 (EMPTY -> Export -> Import -> READY -> rev+1 -> 幂等阻断)
- `TEST-032`: REVIEW_NOT_DUE 必须依赖明确 next_review_at (null / UNKNOWN 阻断，严格未来日期通过且不刷新 actual_checked_at)
- `TEST-033`: NOT_CHECKED 与 BLIND_SPOT 正确持久化 NULL actual_checked_at 且 CHECKED_NONE 缺 actual_checked_at 阻断
- `TEST-034`: Source ADD 缺失 last_verified_at 时自动填充 timezone-aware ISO8601 且二次导出校验通过
- `TEST-035`: 新建 Manual Check 必须使用 local_ref，严禁外部自定义永久 manual_check_id
- `TEST-036`: Benefit UPDATE 增量 patch 与既有记录合并完整校验 (禁止伪造/外来字段，非法枚举/格式阻断)
- `TEST-037`: Lead UPDATE 增量合并校验 (严禁篡改 lead_id 与外来字段，合法更新通过)
- `TEST-038`: Canonical Source UPDATE 增量合并校验 (严禁非法 source_level 与非时区时间戳)
- `TEST-039`: Lead 严禁以 CONFIRMED 长期存在 (必须使用 RESOLVE_TO_BENEFIT 转为正规福利)
- `TEST-044`: CREATE duplicate resolution UPDATE_EXISTING 真实合并入库 (事实更新/保留 first_seen / 保护 User Benefit State / local_ref 映射)
- `TEST-045`: Dedup UNKNOWN-safe 合并防护 (UNKNOWN 不覆盖已有明确事实，显式新值安全更新)
- `TEST-046`: Dedup 目标为 CONFIRMED 时的 Evidence Gate 严格防护
- `TEST-047`: Initial Baseline / Scan Import 内候选福利之间 (Intra-Package) 查重与合并 (MERGE_LOCAL)
- `TEST-048`: Package 内部查重合并后 local_ref 交叉引用映射 (Lead 转福利精准解析)
- `TEST-049`: Package 内部候选福利显式冲突事实检测与结构化告警
- `TEST-050`: 历史 OPEN + CONFIRMED Lead 数据库兼容性检查与 Context 导出安全跳过
- `E2E Lifecycles`:
  - `LIFECYCLE A`: 初始基线全生命周期 (EMPTY -> Export -> DEEP_FULL_SCAN -> READY -> rev=1 -> 二次导入幂等阻断)
  - `LIFECYCLE B`: 正常基线增量更新周期 (READY -> Export -> FULL_SCAN -> UPDATE 覆盖/线索/福利 -> rev=2 -> 5项负向门禁拦截)
  - `LIFECYCLE C`: 查重处理生命周期 (READY -> Export -> CREATE 匹配已有福利 -> Preview 查重 -> 用户选择 UPDATE -> 真实合并更新 -> 保持 ID 与用户状态 -> rev+1)
  - `LIFECYCLE D`: 初始基线 Package 内查重生命周期 (EMPTY -> Export -> DEEP_FULL_SCAN 2条同活动候选 -> Preview 识别 -> MERGE_LOCAL -> 单一福利入库 -> 映射同永久 ID -> READY)



