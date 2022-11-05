import datetime
import math
import os
import sqlite3
from prompt_toolkit.shortcuts import set_title
from prompt_toolkit.shortcuts import message_dialog
from prompt_toolkit.shortcuts import radiolist_dialog
from prompt_toolkit.shortcuts import input_dialog
from prompt_toolkit.styles import Style
from . import nyaq


STYLE = Style.from_dict({
  'button': 'bg:#22ccff',
  'dialog.body': 'bg:#cccccc',
  'frame.label': '#000000',
  'radio-selected': 'bg:#22ccff'
})


def view_page(query, view):
  # View:
  #   infohash - bytes
  #   title - str
  #   category - int
  #   Size - int
  #   Time - int
  #   Trusted - bool/int
  #   Remake - bool/int
  def readable_size(size):
    units = 'BKMGT'
    index = 0
    while size >= 1024:
      size /= 1024
      index += 1
    assert index < len(units)
    return f'{size:.2f}{units[index]}'

  def readable_time(time):
    timetuple = datetime.datetime.utcfromtimestamp(time)
    return timetuple.strftime('%Y-%m-%d')

  return message_dialog(
    title='详情',
    text=(
      f'标题：{view[1]}\n'
      f'特征：{view[0].hex()}\n'
      f'类别：{query.categories[view[2]]}\n'
      f'大小：{readable_size(view[3])}\n'
      f'日期：{readable_time(view[4])}\n'
      f'受信：{"是" if view[5] else "否"}\n'
      f'二创：{"是" if view[6] else "否"}\n'
    ),
    ok_text='确认',
    style=STYLE
  ).run()


def page_page(query, results):
  values = []
  for result in results:
    values.append((result, result[1]))
  default_checked = None
  while True:
    checked = radiolist_dialog(
      title='结果列表',
      text='你想查看哪一个？',
      ok_text='确认',
      cancel_text='退出',
      values=values,
      default=default_checked,
      style=STYLE
    ).run()
    if checked == None:
      break  # 已取消
    default_checked = checked
    view_page(query, checked)


def search_page(query):
  default_keywords = ''
  while True:
    keywords = input_dialog(
      title='搜索',
      text='请输入关键字：',
      ok_text='确认',
      cancel_text='退出',
      default=default_keywords,
      style=STYLE
    ).run()
    if keywords == None:
      break  # 已取消
    default_keywords = keywords
    try:
      count_, limit = query(keywords, count_=True)
    except (sqlite3.OperationalError, AssertionError) as e:
      message_dialog(
        title='搜索出错',
        text=(
          f'{str(e)}\n'
          '\n'
          '试着将 base.regexp 或 base.word 设置为 no？\n'
          r'或者使用 \x20 ''代替空格？\n'
        ),
        ok_text='确认',
        style=STYLE
      ).run()
      continue
    if count_ == 0:
      message_dialog(
        title='未找到任何结果',
        text='未找到任何结果。按 ENTER 继续',
        ok_text='确认',
        style=STYLE
      ).run()
      continue
    # 分页
    max_page = math.ceil(count_ / limit)
    if max_page == 1:
      results = query(keywords, page=1)
      page_page(query, results)
    else:
      values = []
      for p in range(1, max_page + 1):
        values.append((p, f'第{p}页'))
      default_page = 1
      while True:
        page = radiolist_dialog(
          title='页数选择',
          text='你想查看哪一页？',
          ok_text='确认',
          cancel_text='退出',
          values=values,
          default=default_page,
          style=STYLE
        ).run()
        if page == None:
          break  # 已取消
        default_page = page
        results = query(keywords, page=page)
        page_page(query, results)


def modify_page(config, section):
  options = config.options(section)
  options_dict = {}
  values = []
  for option in options:
    option_value = config.get(section, option)
    options_dict[option] = option_value
    values.append((option, f'{option}={option_value}'))
  default_option = None
  while True:
    option = radiolist_dialog(
      title=section,
      text='请选择配置项',
      ok_text='确认',
      cancel_text='退出',
      values=values,
      default=default_option,
      style=STYLE
    ).run()
    if option == None:
      break  # 已取消
    default_option = option
    option_value = input_dialog(
      title=f'{section}.{option}',
      text='请输入数值：',
      ok_text='确认',
      cancel_text='退出',
      default=options_dict[option],
      style=STYLE
    ).run()
    if option_value == None:
      continue  # 已取消
    options_dict[option] = option_value
    # 更新显示
    index = 0
    for value in values:
      if value[0] == option:
        values[index] = (option, f'{option}={option_value}')
        break
      index += 1
  return options_dict


def config_page(query):
  default_checked = None
  while True:
    checked = radiolist_dialog(
      title='配置',
      text='重载、临时修改或是保存配置',
      ok_text='确认',
      cancel_text='退出',
      values=[
        ('reload', '重载'),
        ('modify', '修改'),
        ('save', '保存')
      ],
      default=default_checked,
      style=STYLE
    ).run()
    if checked == None:
      break  # 已取消
    default_checked = checked
    if checked == 'reload':
      query = nyaq.get_query()
      message_dialog(
        title='配置已重载',
        text='配置已重载。按 ENTER 继续',
        ok_text='确认',
        style=STYLE
      ).run()
    elif checked == 'modify':
      config = query.config
      sections = config.sections()
      if len(sections) == 1:
        section = sections[0]
        config.read_dict({
          section: modify_page(config, section)
        })
      else:
        raise NotImplementedError()
      query.clear_cache()
    elif checked == 'save':
      default_name = nyaq.CONFIG_NAME
      while True:
        name = input_dialog(
          title='保存',
          text='请输入文件名：',
          ok_text='确认',
          cancel_text='退出',
          default=default_name,
          style=STYLE
        ).run()
        if name == None:
          break  # 已取消
        default_name = name
        try:
          with open(os.path.expanduser(name), 'w', encoding='utf-8') as file_:
            query.config.write(file_)
            break
        except OSError as e:
          message_dialog(
            title='保存出错',
            text=str(e),
            ok_text='确认',
            style=STYLE
          ).run()
  return query


def about_page():
  message_dialog(
    title='关于',
    text=(
      '编写：urain39\n'
      '版本：v1-alpha\n'
      '更新：2022.11.04\n'
    ),
    ok_text='确认',
    style=STYLE
  ).run()


def main_page():
  set_title('NyaQ - 本地 Nyaa 查询工具')
  query = nyaq.get_query()
  default_checked = None
  while True:
    checked = radiolist_dialog(
      title='主页',
      text='你想做什么？',
      ok_text='确认',
      cancel_text='退出',
      values=[
        ('search', '搜索'),
        ('config', '配置'),
        ('about', '关于')
      ],
      default=default_checked,
      style=STYLE
    ).run()
    if checked == None:
      break  # 已取消
    default_checked = checked
    if checked == 'search':
      search_page(query)
    elif checked == 'config':
      query = config_page(query)
    elif checked == 'about':
      about_page()


if __name__ == '__main__':
  main_page()
