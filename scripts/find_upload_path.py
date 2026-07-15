"""
聚宽上传文件路径查找工具
========================
在聚宽"研究"Notebook中运行本脚本，
它会列出所有能找到 signal_*.json 文件的目录。

使用方法：
  1. 先把 signal_20260715.json 文件上传到聚宽研究环境
  2. 在"研究"Notebook中运行: %run find_upload_path.py
  3. 看输出结果，找到文件所在的目录路径
  4. 如果找不到，本脚本会尝试列出所有可能的目录结构
"""

import os

print('=' * 60)
print('聚宽上传文件路径查找工具')
print('=' * 60)

# 搜索所有可能的目录
candidates = [
    '/home/jquser/upload/',
    '/home/jquser/Research/',
    '/home/jquser/',
    '/tmp/',
    './',
    '../',
]

print('\n搜索 signal_*.json 文件...\n')

found = False
for d in candidates:
    try:
        files = os.listdir(d)
        json_files = [f for f in files if f.startswith('signal_') and f.endswith('.json')]
        if json_files:
            print(f'✅ 找到信号文件在: {d}')
            for f in json_files:
                full = os.path.join(d, f)
                size = os.path.getsize(full)
                print(f'   {f} ({size} bytes)')
                found = True
        else:
            print(f'   {d} → 有{len(files)}个文件，但没有signal文件')
    except FileNotFoundError:
        print(f'   {d} → 目录不存在')
    except PermissionError:
        print(f'   {d} → 无权限访问')
    except Exception as e:
        print(f'   {d} → 错误: {str(e)[:50]}')

if not found:
    print('\n未找到信号文件。请先上传 signal_YYYYMMDD.json 文件。')
    print()
    print('列举所有可访问的顶层目录:\n')
    for d in ['/home/', '/tmp/', '/']:
        try:
            items = os.listdir(d)
            print(f'  {d}: {items[:20]}')
        except:
            print(f'  {d}: 无法访问')

print('\n' + '=' * 60)
print('找到路径后，更新策略文件中的 search_dirs 列表')
print('将正确路径放在 list 最前面')
print('=' * 60)
