-- Migration: 新建 report_quality_audit 表（D.2 LLM-as-judge 报告质量审计）
-- 日期: 2026-05-15
-- 背景:
--   报告生成靠 Agent B 自觉，质量门只能管"格式合规"；语义层面的一致性、
--   可读性、事实性需要让第二个 LLM（judge）来评估。Phase D.2 把审计结果
--   表存起来，便于趋势分析、prompt 调优、A/B 对比。
--   默认 JUDGE_ENABLED=false，需要时再开。

CREATE TABLE IF NOT EXISTS report_quality_audit (
    id                 SERIAL      PRIMARY KEY,
    assessment_id      INTEGER     NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
    prompt_version     TEXT,
    report_version     SMALLINT,
    judge_model        TEXT        NOT NULL,
    coherence_score    SMALLINT    NOT NULL,
    readability_score  SMALLINT    NOT NULL,
    factual_score      SMALLINT    NOT NULL,
    overall_score      SMALLINT    NOT NULL,
    summary            TEXT,
    raw_output         TEXT,
    duration_ms        INTEGER     NOT NULL DEFAULT 0,
    prompt_tokens      INTEGER     NOT NULL DEFAULT 0,
    completion_tokens  INTEGER     NOT NULL DEFAULT 0,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS report_quality_audit_assessment_id_idx
    ON report_quality_audit (assessment_id);
CREATE INDEX IF NOT EXISTS report_quality_audit_created_at_idx
    ON report_quality_audit (created_at DESC);
CREATE INDEX IF NOT EXISTS report_quality_audit_overall_score_idx
    ON report_quality_audit (overall_score);

COMMENT ON TABLE  report_quality_audit                   IS 'Agent B 报告的二次 LLM 评分；驱动质量趋势监控与 prompt 迭代决策';
COMMENT ON COLUMN report_quality_audit.assessment_id     IS '关联 assessments.id；评估对应的报告。assessment 删除时级联删除审计';
COMMENT ON COLUMN report_quality_audit.prompt_version    IS '审计时 Agent B 使用的 prompt 版本（从 assessments.prompt_version 拷过来）；便于按 prompt 版本聚合质量';
COMMENT ON COLUMN report_quality_audit.report_version    IS '审计时报告 Section schema 版本';
COMMENT ON COLUMN report_quality_audit.judge_model       IS '执行审计的 LLM 模型名（默认与 Agent B 同款豆包；可由 JUDGE_MODEL 环境变量覆盖）';
COMMENT ON COLUMN report_quality_audit.coherence_score   IS '一致性评分 1-10：报告是否忠于 diagnosis 输入（type/dimensions/highlights 不漂）';
COMMENT ON COLUMN report_quality_audit.readability_score IS '可读性评分 1-10：语言流畅度、段落组织、用语精准';
COMMENT ON COLUMN report_quality_audit.factual_score     IS '事实性评分 1-10：未编造 diagnosis 没出现的内容、未自相矛盾';
COMMENT ON COLUMN report_quality_audit.overall_score     IS '总评 1-10：综合判断的单一指标，用于趋势主线';
COMMENT ON COLUMN report_quality_audit.summary           IS 'Judge 模型给的一句话总评（≤200 字符），便于运营快速浏览';
COMMENT ON COLUMN report_quality_audit.raw_output        IS 'Judge 的完整输出（含分项理由），用于排查异常审计结果';
COMMENT ON COLUMN report_quality_audit.duration_ms       IS 'Judge 调用耗时（ms），含 LLM 端到端时延';
COMMENT ON COLUMN report_quality_audit.prompt_tokens     IS 'Judge 调用消耗的 prompt token 数；与 ai_call_logs 同口径';
COMMENT ON COLUMN report_quality_audit.completion_tokens IS 'Judge 调用消耗的 completion token 数';
