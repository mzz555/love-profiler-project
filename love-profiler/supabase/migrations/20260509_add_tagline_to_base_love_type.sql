-- Migration: base_love_type 增加 tagline 副标题字段
-- 替代 agent_a._TYPE_MAP 里硬编码的 16×(type_name, type_tagline)。
-- 改完后 enrich 阶段从 DB 拉 tagline 注入 diagnosis，agent_a 不再持有这份字典。

ALTER TABLE base_love_type ADD COLUMN IF NOT EXISTS tagline TEXT NOT NULL DEFAULT '';

COMMENT ON COLUMN base_love_type.tagline IS '类型副标题，用于报告头部；与 type_name 同源，单源真相在此表';

UPDATE base_love_type SET tagline = '你不需要完美，就值得被爱'             WHERE type_code = 'S-CL-H';
UPDATE base_love_type SET tagline = '安定是你的底色，温柔是你的选择'         WHERE type_code = 'S-CL-MH';
UPDATE base_love_type SET tagline = '爱与不安交织，而你依然在靠近'           WHERE type_code = 'S-CL-MP';
UPDATE base_love_type SET tagline = '边界模糊，但底色坚定'                 WHERE type_code = 'S-BL-H';
UPDATE base_love_type SET tagline = '保持热忱，在这之间慢慢来'             WHERE type_code = 'MS-CL-H';
UPDATE base_love_type SET tagline = '你的裂缝里，开始有光透进来了'           WHERE type_code = 'MS-CL-MH';
UPDATE base_love_type SET tagline = '想要稳妥，也不怕磕碰'                 WHERE type_code = 'MS-CL-MP';
UPDATE base_love_type SET tagline = '你的温柔，不需要锋利轮廓'             WHERE type_code = 'MS-BL-H';
UPDATE base_love_type SET tagline = '在安全的距离里，慢慢靠近'             WHERE type_code = 'M-CL-MH';
UPDATE base_love_type SET tagline = '不确定的时候，你选择观察而非投入'       WHERE type_code = 'M-CL-MP';
UPDATE base_love_type SET tagline = '你的光谱尚未定型，每一种可能都属于你'   WHERE type_code = 'M-M-M';
UPDATE base_love_type SET tagline = '敏感是你的雷达，也是你的铠甲'         WHERE type_code = 'MA-CL-H';
UPDATE base_love_type SET tagline = '伤痛让你更敏锐，而非更脆弱'           WHERE type_code = 'MA-CL-MH';
UPDATE base_love_type SET tagline = '你的柔软，有时只是为了不被拒绝'       WHERE type_code = 'MA-CL-MP';
UPDATE base_love_type SET tagline = '你知道自己的脆弱，却没有后退'         WHERE type_code = 'MA-BL-H';
UPDATE base_love_type SET tagline = '深爱过也受伤过，但你仍然选择相信'     WHERE type_code = 'MA-BL-MP';
UPDATE base_love_type SET tagline = '你的爱很深，深到自己都害怕'           WHERE type_code = 'A-CL-H';
UPDATE base_love_type SET tagline = '在乎到极致，反而先一步推开'           WHERE type_code = 'A-CL-MP';
UPDATE base_love_type SET tagline = '渴望紧密，也知道自己的边界'           WHERE type_code = 'A-BL-H';
UPDATE base_love_type SET tagline = '你如此渴望被爱，以至于忘了自己'       WHERE type_code = 'A-BL-P';
UPDATE base_love_type SET tagline = '你害怕失去，所以选择先说再见'         WHERE type_code = 'A-BL-MP';
