"""Diagnosis pydantic schema（Phase A.1）。

校验 /quiz/submit enrich 阶段之后、写入 assessments.diagnosis_json 之前的字典。
任意 DB 富化（base_love_type / base_D4_type / base_D5_quadrant / highlights / segment_decode）
返回 None 或字段缺失，都会在此处被显式拒绝，避免 prompt 静默退化。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


Severity = Literal["high", "moderate", "info"]


class D4Detail(BaseModel):
    """base_D4_type 表富化结果，对应一个爱的语言类型（T1~T5）。"""

    model_config = ConfigDict(extra="allow")

    code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    detail: str = Field(min_length=1)


class HighlightEnriched(BaseModel):
    """highlights 表富化结果，单条诊断高亮。"""

    model_config = ConfigDict(extra="allow")

    code: str = Field(min_length=1)
    name_cn: str = Field(min_length=1)
    severity: Severity
    is_positive: bool
    report_seed: str = Field(min_length=1)
    interp_path: str = Field(min_length=1)
    trigger_condition: str = Field(min_length=1)


class SegmentDecode(BaseModel):
    """base_segment_decode 表富化结果，D1/D2/D3 段落解码。"""

    model_config = ConfigDict(extra="allow")

    dimension: Literal["D1", "D2", "D3"]
    code: str = Field(min_length=1)
    label_cn: str = Field(min_length=1)
    is_healthy: bool


class D1Block(BaseModel):
    model_config = ConfigDict(extra="allow")
    interp: str = Field(min_length=1)
    raw: int


class D2Block(BaseModel):
    model_config = ConfigDict(extra="allow")
    interp: str = Field(min_length=1)
    raw: int


class D3Block(BaseModel):
    model_config = ConfigDict(extra="allow")
    interp: str = Field(min_length=1)
    raw: int
    pursue_avoid: str = Field(min_length=1)


class D4Block(BaseModel):
    model_config = ConfigDict(extra="allow")
    top2: list[str] = Field(min_length=1, max_length=2)
    normalized: dict[str, float]
    declared: str | None = None
    aligned: bool


class D5Block(BaseModel):
    model_config = ConfigDict(extra="allow")
    quadrant: str
    style: str
    s1: str
    s2: str
    s1_raw: int
    s2_raw: int


class DimensionsBlock(BaseModel):
    """五维度容器，缺任何一维都拒绝。"""

    model_config = ConfigDict(extra="allow")

    D1: D1Block
    D2: D2Block
    D3: D3Block
    D4: D4Block
    D5: D5Block


class Diagnosis(BaseModel):
    """enrich 后写库前的 diagnosis 字典契约。"""

    model_config = ConfigDict(extra="allow")

    type_code: str = Field(min_length=1)
    type_name: str = Field(min_length=1)
    type_anchor: str = Field(min_length=10)
    type_tagline: str = ""
    dimensions: DimensionsBlock
    D4_details: list[D4Detail] = Field(min_length=1)
    D5_guide: str = ""
    D5_style_name: str = ""
    segment_decode: list[SegmentDecode] = Field(default_factory=list)
    highlights: list[HighlightEnriched] = Field(default_factory=list)
    question_set_version: str = ""

    @model_validator(mode="after")
    def _validate_d4_alignment(self) -> "Diagnosis":
        top2 = self.dimensions.D4.top2
        detail_codes = {d.code for d in self.D4_details}
        missing = [c for c in top2 if c not in detail_codes]
        if missing:
            raise ValueError(
                f"D4_details 缺失 top2 中的代码：{missing}（top2={top2}）"
            )
        return self

    @model_validator(mode="after")
    def _validate_d5_guide(self) -> "Diagnosis":
        if self.dimensions.D5.quadrant and not self.D5_guide:
            raise ValueError(
                f"D5_guide 不能为空（quadrant={self.dimensions.D5.quadrant!r}）"
            )
        return self
