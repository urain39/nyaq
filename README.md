本地 Nyaa 查询工具（半成品）
========================

### 数据库结构
```sql
-- Categories
CREATE TABLE IF NOT EXISTS categories (
  -- 主(4bit) | 次(4bit)
  id TINYINT PRIMARY KEY,
  name TEXT UNIQUE NOT NULL
);

-- Torrents
CREATE TABLE IF NOT EXISTS torrents (
  -- Use hex(infohash) to convert
  infohash BLOB PRIMARY KEY,
  title TEXT NOT NULL,
  category TINYINT NOT NULL,
  size INTEGER NOT NULL,
  time INTEGER NOT NULL,
  trusted BOOLEAN NOT NULL,
  remake BOOLEAN NOT NULL
);
```

### 如何使用？

1. 根据上面的数据结构创建你自己的数据库

2. 在终端中执行以下命令
```
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m nyaq
```

### 特性列表

- [x] 分页浏览
- [x] 设置页面
- [ ] 热词列表（以及补全）
- [ ] 支持 OpenCC
- [ ] JSON 接口（CSV 风格？）
