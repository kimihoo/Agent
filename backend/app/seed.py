"""演示数据初始化：用户、知识库、制度文档、审核规则、示例合同。"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import select

from .config import UPLOAD_DIR
from .db import SessionLocal
from .models import Contract, Document, KBPermission, KnowledgeBase, Rule, User
from .security import hash_password
from .services.audit import log
from .services.ingestion import ingest_document
from .services.parser import parse_file
from .routers.contracts import analyze_contract

USERS = [
    ("admin", "admin123", "系统管理员", "综合部", "admin"),
    ("hr", "hr123", "张敏（人事）", "人力资源部", "hr"),
    ("fin", "fin123", "李强（财务）", "财务部", "finance"),
    ("legal", "legal123", "王琳（法务）", "法务部", "legal"),
    ("emp", "emp123", "陈晨（市场）", "市场部", "employee"),
]

RULES = [
    ("R001", "合同主体信息", "条款完整性", "high", "required_clause", {"clause_type": "party"},
     "未识别到合同主体（甲乙双方）信息", "《合同审核管理办法》二（一）"),
    ("R002", "标的与服务范围", "条款完整性", "high", "required_clause", {"clause_type": "subject"},
     "合同缺少标的、服务内容或工作范围条款", "《合同审核管理办法》二（二）"),
    ("R003", "价款与支付方式", "条款完整性", "high", "required_clause", {"clause_type": "payment"},
     "合同缺少价款、支付方式或结算条款", "《合同审核管理办法》二（三）"),
    ("R004", "履行期限", "条款完整性", "medium", "required_clause", {"clause_type": "term"},
     "合同缺少履行期限或有效期约定", "《合同审核管理办法》二（四）"),
    ("R005", "违约责任", "条款完整性", "high", "required_clause", {"clause_type": "liability"},
     "合同缺少违约责任条款", "《合同审核管理办法》二（五）"),
    ("R006", "保密条款", "条款完整性", "medium", "required_clause", {"clause_type": "confidentiality"},
     "合同缺少保密条款", "《合同审核管理办法》二（六）"),
    ("R007", "争议解决", "条款完整性", "high", "required_clause", {"clause_type": "dispute"},
     "合同缺少争议解决条款", "《合同审核管理办法》二（八）"),
    ("R008", "验收标准", "条款完整性", "medium", "required_clause", {"clause_type": "acceptance"},
     "合同未约定验收标准或交付物要求", "《合同审核管理办法》二（九）"),
    ("R009", "知识产权归属", "条款完整性", "low", "required_clause", {"clause_type": "ip"},
     "合同未约定知识产权归属", "《合同审核管理办法》二（七）"),
    ("R010", "争议解决方式明确", "条款有效性", "high", "keyword_any",
     {"clause_type": "dispute", "keywords": ["仲裁", "诉讼", "法院"]},
     "争议解决条款未明确约定仲裁或诉讼方式", "《合同审核管理办法》二（八）"),
    ("R011", "付款账期超限", "财务合规", "medium", "max_number",
     {"field": "payment_days", "limit": 60},
     "付款账期 {value} 天，超过制度上限 {limit} 天", "《合同审核管理办法》二（三）"),
    ("R012", "违约金比例过高", "财务合规", "medium", "max_number",
     {"field": "penalty_ratio", "limit": 20},
     "违约金比例 {value}%，超过制度上限 {limit}%", "《合同审核管理办法》二（五）"),
    ("R013", "预付款比例过高", "财务合规", "high", "max_number",
     {"field": "prepay_ratio", "limit": 30},
     "预付比例 {value}%，超过制度上限 {limit}%", "《合同审核管理办法》二（三）"),
    ("R014", "永久或无限期保密", "风险表述", "high", "keyword_none",
     {"keywords": ["永久保密", "无限期保密", "永久性保密"]},
     "合同约定永久或无限期保密，存在履约风险", "《合同审核管理办法》二（六）"),
    ("R015", "自动续约条款", "风险表述", "low", "keyword_none",
     {"keywords": ["自动续约", "自动展期"]},
     "合同包含自动续约/展期约定，需确认审批机制", "《合同审核管理办法》三"),
]

_DOCS = {
    "人力资源制度库": (
        "员工考勤与请假管理制度",
        """# 员工考勤与请假管理制度
文件编号：HR-2024-001
适用范围：公司全体正式员工及试用期员工。

一、工作时间
公司实行标准工时制，每日工作 8 小时，每周工作 5 天，通常工作时间为 9:00—18:00，午休 1 小时。因业务需要调整作息的，由部门负责人报人力资源部备案。

二、考勤打卡
员工须通过企业微信或 OA 系统进行上下班打卡。每日打卡两次，漏打卡须在 3 个工作日内提交补卡申请，经直属上级审批后生效。每月补卡次数原则上不超过 3 次。

三、请假类型与审批权限
1. 年休假：员工累计工作满 1 年不满 10 年的，年休假 5 天；满 10 年不满 20 年的，10 天；满 20 年的，15 天。年休假需提前 3 个工作日通过 OA 系统提交申请，经直属上级审批；连续休假 5 天以上的，还需部门负责人审批。
2. 病假：需提供二级以上医院出具的证明。病假 3 天以内由直属上级审批，3 天以上须报人力资源部备案。
3. 事假：按小时或按天申请，事假期间不计发工资。单次事假不超过 3 天，全年累计不超过 15 天。
4. 婚假、产假、陪产假、丧假等法定假期，按国家和当地最新规定执行，申请时须上传相应证明材料。

四、迟到、早退与旷工
每月迟到或早退累计不超过 3 次且每次不超过 30 分钟的，给予提醒；超过的按公司奖惩制度处理。未履行请假手续且未出勤的，按旷工处理。

五、加班与调休
加班须提前在 OA 提交加班申请并经审批。工作日加班可申请调休，调休须在 3 个月内使用；法定节假日加班按国家规定支付加班工资。

六、解释与生效
本制度由人力资源部负责解释，自发布之日起施行。""",
    ),
    "财务报销制度库": (
        "费用报销管理办法",
        """# 费用报销管理办法
文件编号：FIN-2024-003
适用范围：公司全体员工。

一、报销范围
因公发生的差旅费、交通费、业务招待费、办公费、培训费等，凭合法有效发票据实报销。个人消费、罚款、礼品等不得报销。

二、差旅费标准
（一）住宿费：一线城市（北京、上海、广州、深圳）每人每晚不超过 600 元；其他城市每人每晚不超过 400 元。超标部分由个人承担。
（二）城市间交通：优先选择高铁二等座或经济舱；特殊情况需乘坐一等座或商务舱的，须提前审批。
（三）市内交通：据实报销，单日累计超过 200 元的需说明事由。
（四）伙食补助：每人每天 100 元，按实际出差天数计发，不需提供餐饮发票。

三、报销流程与时限
员工应在费用发生后 30 日内通过 OA 系统提交报销单，上传发票原件照片，并填写成本中心。逾期超过 90 天的原则上不予受理。
审批链路：直属上级 → 部门负责人 → 财务审核 → 出纳付款。单笔金额超过 5000 元的，需财务经理审批；超过 20000 元的，需总经理审批。
报销款项一般在审批完成后 5 个工作日内支付至员工工资卡。

四、发票要求
发票抬头必须为公司全称，税号准确；电子发票需上传 PDF 原件并避免重复报销。增值税专用发票须在开具后 30 日内交财务认证。

五、违规处理
虚报、重复报销或伪造发票的，除追回款项外，按公司奖惩制度处理；情节严重的，依法追究责任。

六、解释与生效
本办法由财务部负责解释，自发布之日起施行。""",
    ),
    "信息系统操作手册": (
        "OA 与办公系统操作手册",
        """# 信息系统操作手册
适用系统：OA 协同办公系统、企业邮箱、VPN、财务共享平台。

一、OA 系统登录
在浏览器访问 https://oa.example.com，使用企业邮箱账号登录。首次登录需修改初始密码并绑定手机号。忘记密码可点击“找回密码”，或联系信息中心重置。

二、提交报销单
1. 登录 OA，进入“工作台 - 费用报销 - 新建报销单”。
2. 选择报销类型（差旅、交通、招待、办公等），填写事由、金额和成本中心。
3. 上传发票图片或 PDF，系统会自动识别发票号码并查重。
4. 选择审批人后提交，可在“我的申请”中查看审批进度。
5. 审批通过后，财务出纳在 5 个工作日内打款，可在“报销记录”中查询付款状态。

三、请假申请
进入“工作台 - 人事 - 请假申请”，选择假期类型和起止时间，填写事由并上传证明（病假等），提交后由直属上级审批。审批结果通过企业微信通知。

四、VPN 使用
外网访问内网系统需先连接 VPN。下载安装客户端后，使用工号和动态口令登录。连续 5 次输错密码账号将被锁定 30 分钟，可联系信息中心解锁。

五、密码与账号安全
密码长度不少于 12 位，须包含大小写字母、数字和符号，每 90 天更换一次。严禁共享账号或将密码告知他人。发现异常登录请立即修改密码并报信息中心。

六、常见问题
1. 附件上传失败：检查文件是否超过 20MB，或更换 Chrome/Edge 浏览器。
2. 审批人显示为空：确认组织架构是否已同步，联系部门行政。
3. 系统页面空白：清理浏览器缓存后重试。

七、服务支持
信息中心服务台电话：8888；工作日 9:00—18:00。紧急故障可通过企业微信“IT 服务台”提交工单。""",
    ),
    "合同与法务规范库": (
        "合同审核管理办法",
        """# 合同审核管理办法
文件编号：LEG-2024-002
适用范围：公司及下属单位对外签订的各类合同、协议及备忘录。

一、管理职责
业务部门负责合同起草与履约管理；法务部负责条款合法合规审核；财务部负责价款、税务与支付条件复核；用印管理员负责用印登记与归档。

二、合同必备条款
（一）合同主体：应写明甲乙双方全称、统一社会信用代码、法定代表人或授权代表及联系方式。
（二）标的与服务范围：应明确服务内容、数量、质量标准与交付物清单。
（三）价款与支付：应明确合同金额、计价方式、发票类型和付款节点。付款账期原则上不超过 60 日，预付款比例不得超过合同总额的 30%。
（四）履行期限：应明确合同生效时间、服务期限和交付节点。
（五）违约责任：应约定逾期交付、质量不合格等情形的违约责任。违约金比例原则上不超过合同总额的 20%。
（六）保密条款：应明确保密范围、保密期限和违约责任，不得约定永久保密或无限期保密。
（七）知识产权：应明确履约过程中形成的成果归属及使用许可范围。
（八）争议解决：应明确约定仲裁或诉讼，并写明具体的仲裁机构或有管辖权的法院，不得含糊约定。
（九）验收标准：应约定验收方式、验收期限和不合格的处理方式。

三、禁止性条款
不得约定自动续约、自动展期而未经审批；不得约定放弃公司主要权利、无条件接受对方单方变更的条款；不得约定由对方单方决定验收结果。

四、审核流程
业务部门发起 → 法务初审（1—3 个工作日）→ 财务复核 → 分管领导审批 → 用印 → 归档。合同金额超过 100 万元的，须经总经理办公会审议。

五、用印与归档
合同用印须在 OA 提交用印申请并附最终版本。合同正本至少留存两份，由法务部统一归档，保存期限不少于合同终止后 5 年。

六、解释与生效
本办法由法务部负责解释，自发布之日起施行。""",
    ),
    "运营管理制度库": (
        "运营管理制度与资料查询指引",
        """# 运营管理制度与资料查询指引
文件编号：OPS-2024-005
适用范围：运营部及各业务部门运营接口人。

一、月度经营分析报告
每月 5 日前，运营部汇总上月核心经营指标，形成《月度经营分析报告》，提交管理层审阅。各业务部门须在每月 3 日前提交本部门数据及分析说明。

二、数据口径与来源
1. 收入数据以财务确认的营业收入为准，统计口径为含税收入。
2. 用户数据以数据中台“用户资产”主题域为准，日活按自然日去重统计。
3. 各业务线不得自行修改口径；如需调整，须经运营部与财务部共同确认并留存记录。

三、运营资料存放
经营看板：https://bi.example.com（需 VPN 访问）。
制度与模板：OA“知识中心 - 运营资料”目录，包含周报模板、活动复盘模板、渠道分析模板。
历史报告：共享盘 \\\\fileserver\\ops\\reports，按“年份/月份”归档。

四、跨部门协作
涉及产品、市场、财务的联合项目，须在项目启动前明确目标、指标、负责人和里程碑，并在 OA 建立项目空间。周例会纪要于会后 1 个工作日内上传项目空间。

五、数据安全
经营数据仅限内部使用，不得对外提供或截图外传。对外披露须经营运营部和管理层审批。

六、解释与生效
本制度由运营部负责解释，自发布之日起施行。""",
    ),
}

_SAMPLE_CONTRACT = """技术服务合同

合同编号：HT-2024-0918
甲方：星云数字科技有限公司
乙方：智维信息技术有限公司

第一条 服务内容
乙方向甲方提供数据平台运维与技术支持服务，包括系统巡检、故障处理、版本升级及技术咨询，服务范围详见附件一《服务清单》。

第二条 合同金额与支付
本合同服务费总额为人民币 480,000 元（大写：肆拾捌万元整）。合同签订后 5 个工作日内，甲方向乙方支付合同总额的 40% 作为预付款；剩余款项在服务期满后 90 日内一次性支付。乙方应开具增值税专用发票。

第三条 服务期限
服务期限自 2024 年 10 月 1 日起至 2025 年 9 月 30 日止，共计 12 个月。

第四条 双方权利义务
甲方应按约定支付服务费用，并提供必要的办公与系统接入条件。乙方应指派不少于 3 名技术人员提供服务，并保证响应时间不超过 2 小时。

第五条 违约责任
任何一方违反本合同约定的，应向守约方支付合同总额 30% 的违约金；违约金不足以弥补损失的，还应赔偿实际损失。

第六条 保密条款
双方对在合作过程中知悉的对方商业秘密承担永久保密义务，未经对方书面同意不得向任何第三方披露。

第七条 知识产权
乙方在提供服务过程中形成的技术文档与工具的知识产权归乙方所有，甲方在服务期内享有使用权。

第八条 争议解决
因本合同引起的争议，双方应友好协商解决；协商不成的，提交甲方所在地有管辖权的人民法院处理。

第九条 其他
本合同一式两份，双方各执一份，自双方盖章之日起生效。服务期满后，如双方均未提出异议，本合同自动续约一年。

甲方（盖章）：星云数字科技有限公司
乙方（盖章）：智维信息技术有限公司
签订日期：2024 年 9 月 18 日
"""


def seed() -> None:
    db = SessionLocal()
    try:
        if db.execute(select(User.id)).first():
            return

        users: dict[str, User] = {}
        for username, password, display_name, department, role in USERS:
            user = User(
                username=username,
                password_hash=hash_password(password),
                display_name=display_name,
                department=department,
                role=role,
            )
            db.add(user)
            users[username] = user
        db.flush()

        for code, name, category, severity, kind, params, message, basis in RULES:
            db.add(Rule(
                code=code,
                name=name,
                category=category,
                severity=severity,
                kind=kind,
                params=json.dumps(params, ensure_ascii=False),
                message=message,
                legal_basis=basis,
            ))
        db.flush()

        kbs: dict[str, KnowledgeBase] = {}
        kb_meta = [
            ("人力资源制度库", "请假、考勤、入离职等人力资源制度", "人力资源部", "internal"),
            ("财务报销制度库", "差旅、报销、付款与发票规范", "财务部", "internal"),
            ("信息系统操作手册", "OA、邮箱、VPN 等系统操作指引", "信息技术部", "internal"),
            ("合同与法务规范库", "合同审核规范、法务制度（受限访问）", "法务部", "restricted"),
            ("运营管理制度库", "经营分析、数据口径与资料存放规范", "运营部", "internal"),
        ]
        for name, description, department, visibility in kb_meta:
            kb = KnowledgeBase(
                name=name,
                description=description,
                department=department,
                visibility=visibility,
                created_by=users["admin"].id,
            )
            db.add(kb)
            kbs[name] = kb
        db.flush()

        db.add(KBPermission(kb_id=kbs["合同与法务规范库"].id, principal_type="role",
                            principal="finance", permission="read"))
        db.add(KBPermission(kb_id=kbs["合同与法务规范库"].id, principal_type="user",
                            principal="legal", permission="write"))
        db.flush()

        for kb_name, (title, content) in _DOCS.items():
            kb = kbs[kb_name]
            stored = UPLOAD_DIR / f"seed_{uuid.uuid4().hex}.md"
            stored.write_text(content, encoding="utf-8")
            doc = Document(
                kb_id=kb.id,
                title=title,
                filename=f"{title}.md",
                stored_path=str(stored),
                mime="text/markdown",
                size=len(content.encode()),
                uploaded_by=users["admin"].id,
            )
            db.add(doc)
            db.commit()
            ingest_document(db, doc)

        contract_path = UPLOAD_DIR / "seed_contract.txt"
        contract_path.write_text(_SAMPLE_CONTRACT, encoding="utf-8")
        contract = Contract(
            title="数据平台运维技术服务合同（示例）",
            filename="技术服务合同-示例.txt",
            stored_path=str(contract_path),
            status="analyzing",
            uploaded_by=users["legal"].id,
        )
        db.add(contract)
        db.commit()
        parsed = parse_file(contract_path, contract.filename)
        analyze_contract(db, contract, parsed.full_text)
        log(db, users["admin"].id, "system.seed", "system", "demo", "演示数据初始化完成")
        db.commit()
    finally:
        db.close()
