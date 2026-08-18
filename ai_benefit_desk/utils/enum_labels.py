"""Enum labels and translations for UI presentation."""

VERIFICATION_STATUS_LABELS = {
    "CONFIRMED": "已确认",
    "LIKELY": "较高可信",
    "UNVERIFIED": "未验证",
    "DISPUTED": "存在争议",
}

STATUS_LABELS = {
    "ACTIVE": "有效",
    "EXPIRING_SOON": "即将过期",
    "EXPIRED": "已过期",
    "UPCOMING": "即将开始",
    "WAITLIST": "候补 / 等待开放",
    "ENDED": "已结束",
    "UNKNOWN": "状态未知",
}

CHANGE_TYPE_LABELS = {
    "NEW": "新增",
    "NO_CHANGE": "无变化",
    "RESTORED": "恢复上线",
    "EXPANDED": "权益扩大",
    "REDUCED": "权益缩减",
    "EXTENDED": "活动延期",
    "SHORTENED": "活动缩短",
    "DISCOUNTED": "降价/折扣",
    "PRICE_INCREASED": "价格上涨",
    "ELIGIBILITY_EXPANDED": "资格扩大",
    "ELIGIBILITY_REDUCED": "资格收紧",
    "STATUS_CHANGED": "状态改变",
    "IMPORTANT_RULE_CHANGE": "重要规则变动",
    "ENDED": "活动结束",
    "UNKNOWN": "未知",
}

COVERAGE_STATE_LABELS = {
    "CHECKED_FOUND": "已检查·有发现",
    "CHECKED_NONE": "已检查·暂无发现",
    "REVIEW_NOT_DUE": "复查未到期",
    "NOT_CHECKED": "待检查",
    "BLIND_SPOT": "监控盲区",
    "NOT_APPLICABLE": "不适用",
}

SCAN_COMPLETION_LABELS = {
    "PUBLIC_COMPLETE": "公开扫描完成",
    "OVERALL_PARTIAL": "总体覆盖部分完成",
    "SCAN_INCOMPLETE": "扫描未完成",
}

USER_ACTION_STATE_LABELS = {
    "NOT_REVIEWED": "待处理",
    "INTERESTED": "感兴趣",
    "CLAIMED": "已领取",
    "NOT_ELIGIBLE": "不符合资格",
    "SKIPPED": "已跳过",
}

LEAD_STATUS_LABELS = {
    "OPEN": "开放待处理",
    "RESOLVED": "已转正式福利",
    "REJECTED": "已驳回",
}

SOURCE_STATUS_LABELS = {
    "ACTIVE": "有效",
    "DEPRECATED": "已停用",
}

SOURCE_LEVEL_LABELS = {
    "S": "S级 (官方文档/定价/规则)",
    "A": "A级 (官方社区/员工/邮件)",
    "B": "B级 (合作伙伴/开发者社区)",
    "C": "C级 (第三方社区/用户帖子)",
}

MANUAL_CHECK_CHANNEL_LABELS = {
    "ACCOUNT": "账号中心",
    "DASHBOARD": "控制台/后台",
    "APP": "移动端应用",
    "DESKTOP": "桌面客户端",
    "IDE": "IDE环境/插件",
    "EMAIL": "邮件通知",
    "CHECKOUT": "结账/续费页",
    "OTHER": "其他渠道",
}

MANUAL_CHECK_PRIORITY_LABELS = {
    "LOW": "低",
    "MEDIUM": "中",
    "HIGH": "高",
}

MANUAL_CHECK_STATUS_LABELS = {
    "OPEN": "待检查",
    "COMPLETED": "已完成",
    "DISMISSED": "已忽略",
}

RISK_LEVEL_LABELS = {
    "NONE": "无风险",
    "LOW": "低风险",
    "MEDIUM": "中风险",
    "HIGH": "高风险",
    "UNKNOWN": "未知",
}

BENEFIT_OP_LABELS = {
    "CREATE": "新增福利",
    "UPDATE": "更新福利",
    "CONFIRM_NO_CHANGE": "复核无变化",
}

LEAD_OP_LABELS = {
    "CREATE": "新增线索",
    "UPDATE": "更新线索",
    "RESOLVE_TO_BENEFIT": "升级为福利",
    "REJECT": "驳回线索",
}

SOURCE_OP_LABELS = {
    "ADD": "新增入口",
    "UPDATE": "更新入口",
    "DEPRECATE": "停用入口",
}

def get_label(mapping: dict, key: str, default: str = None) -> str:
    """Helper to get translated Chinese label safely."""
    if key is None:
        return default or "-"
    return mapping.get(str(key), default or str(key))
