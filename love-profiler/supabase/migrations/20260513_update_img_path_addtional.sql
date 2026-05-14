-- Migration: 将 base_love_type.img_path 更新为新目录 static/addtional
-- 文件命名规则：character_XX_lively.png，XX 与表 id 对齐（两位零填充）

UPDATE base_love_type
SET img_path = '/static/addtional/character_' || LPAD(id::text, 2, '0') || '_lively.png';
