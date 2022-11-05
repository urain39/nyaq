import configparser
import functools
import math
import os
import re
import sqlite3


CONFIG_NAME = '.nyaqrc'
CONFIG_PATHS = [
  # Global
  os.path.expanduser(f'~/{CONFIG_NAME}'),
  # Local
  CONFIG_NAME
]
DATABASE_NAME = '.nyaq.db'


def _load_config():
  '''加载配置。
  '''
  cfgpsr = configparser.ConfigParser()
  cfgpsr.read_dict({
    'base': {
      'database': '~/.nyaq.db',
      'category': 'unset',
      'whole': 'no',
      'regexp': 'no',
      'word': 'no',
      'size': '0B:20G',
      'recent': 'unset',
      'trusted': 'unset',
      'remake': 'unset',
      'order': 'time:desc',
      'limit': '30',
      'hotword': '0',
      'nonword': 'yes'
    }
  })
  cfgpsr.read(CONFIG_PATHS)
  return cfgpsr


def _load_database(cfgpsr):
  '''加载数据库。
  '''
  database = cfgpsr.get('base', 'database')
  db = sqlite3.connect(os.path.expanduser(database))
  db.create_function('regexp', 2,
    lambda r, s: re.search(r, s, re.IGNORECASE) != None)
  return db


def _build_query(cfgpsr, kwds=None, count_=False):
  '''构造 SQL 查询语句。
  '''
  def config_get(name, type_=str, default=None):
    if not cfgpsr.has_option('base', name):
      return default
    try:
      if type_ == bool:
        return cfgpsr.getboolean('base', name)
      if type_ == int:
        return cfgpsr.getint('base', name)
      if type_ == float:
        return cfgpsr.getfloat('base', name)
    except ValueError:
      return default
    # str or others
    return cfgpsr.get('base', name)

  def size_parse(size, default=0):
    match = re.match(r'^(\d+)(b|k|m|g|t)$', size.lower())
    if not match:
      return default
    number, unit = match.groups()
    factor = 0
    if unit == 'b':
      factor = 1 << 0
    elif unit == 'k':
      factor = 1 << 10
    elif unit == 'm':
      factor = 1 << 20
    elif unit == 'g':
      factor = 1 << 30
    elif unit == 't':
      factor = 1 << 40
    else:
      raise Exception('too large or too small')
    return math.ceil(float(number) * factor)

  # ---------------------------------------------------------------------------

  qbuf = [
    'SELECT count(*) FROM torrents' \
      if count_ \
      else 'SELECT * FROM torrents'
  ]
  cbuf = []  # 条件
  ebuf = []  # 实体

  # ---------------------------------------------------------------------------

  # Keywords
  if kwds != None:
    whole = config_get('whole', type_=bool, default=False)
    if whole:
      kwds = [kwds]
    else:
      kwds = kwds.split(' ')
    regexp = config_get('regexp', type_=bool, default=False)
    for kwd in kwds:
      if regexp:
        cbuf.append('regexp(?, title)')
        ebuf.append(kwd)
      else:
        word = config_get('word', type_=bool, default=False)
        if word:
          assert re.match(r'^\w*$', kwd) != None
          cbuf.append('regexp(?, title)')
          ebuf.append(fr'\b{kwd}\b')
        else:
          nonword = config_get('nonword', type_=bool, default=True)
          if nonword and re.match(r'^[^a-z]*$', kwd, re.IGNORECASE) != None:
            cbuf.append('instr(title, ?)')
            ebuf.append(kwd)
          else:
            cbuf.append('instr(lower(title), ?)')
            ebuf.append(kwd.lower())

  # Category
  category = config_get('category', type_=int, default=-1)
  if 0 <= category <= 15:
    cbuf.append('category >> 4 == ?')
    ebuf.append(category)

  # Size
  size = config_get('size', type_=str, default='')
  if ':' in size:
    size_min, size_max = size.split(':')
    cbuf.append('size >= ?')
    ebuf.append(size_parse(size_min, 0))
    cbuf.append('size <= ?')
    ebuf.append(size_parse(size_max, 1 << 34))

  # Recent
  recent = config_get('recent', type_=int, default=-1)
  if recent >= 1:
    cbuf.append(f'time >= strftime("%s", "now", "-{recent} days", "utc")')

  # Trusted
  trusted = config_get('trusted', type_=bool, default=None)
  if trusted != None:
    cbuf.append('trusted == ?')
    ebuf.append(trusted)

  # Remake
  remake = config_get('remake', type_=bool, default=None)
  if remake != None:
    cbuf.append('remake == ?')
    ebuf.append(remake)

  # ---------------------------------------------------------------------------

  if cbuf:
    qbuf.append('WHERE')
    qbuf.append(' AND '.join(cbuf))

  # Order
  order = config_get('order', type_=str, default='')
  if ':' not in order:
    order = ':'
  order_by, order_modifier = order.lower().split(':')
  if order_by not in ('title', 'size', 'time'):
    order_by = 'time'
  if order_modifier not in ('asc', 'desc'):
    order_modifier = 'desc'
  qbuf.append(f'ORDER BY {order_by} {order_modifier}')

  # Limit
  limit = config_get('limit', type_=int, default=-1)
  if not 1 <= limit <= 80:
    limit = 40
  if not count_:
    qbuf.append('LIMIT ? OFFSET ?')
    ebuf.append(limit)
    ebuf.append(0)

  return ' '.join(qbuf), ebuf, limit


# 使用闭包代替类封装；同时解决 _build_query 因参数类型限制而无法缓存的问题
def get_query():
  cfg = _load_config()
  db = _load_database(cfg)
  cats = dict(db.execute('SELECT * FROM categories').fetchall())

  # 注意：返回的 ebuf 是缓存后共享的；请尽量减少对其进行直接修改
  @functools.lru_cache(128)
  def build_query(kwds, count_):
    return _build_query(cfg, kwds, count_=count_)

  def query(kwds=None, count_=False, page=1):
    q, ebuf, limit = build_query(kwds, count_=count_)
    if count_:
      return db.execute(q, ebuf).fetchone()[0], limit
    assert page > 0
    # 共享的 ebuf 会带有上次的 offset；所以这里我们不能直接跳过 page 为1的情况
    ebuf[-1] = (page - 1) * ebuf[-2]  # offset = (page-1) * limit
    return db.execute(q, ebuf).fetchall()
  query.config = cfg
  query.categories = cats  # Nyaa!
  query.clear_cache = build_query.cache_clear

  return query
