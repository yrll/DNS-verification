import os
from pathlib import Path

def replace_in_file(file_path, replacements):
    # 读取文件内容
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()

    # 替换文件内容中的特定字符串
    for old, new in replacements.items():
        content = content.replace(old, new)

    # 写回文件
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write(content)

def rename_file(file_path, replacements):
    # 构造新的文件名
    new_name = file_path.name
    for old, new in replacements.items():
        new_name = new_name.replace(old, new)

    # 重命名文件
    new_file_path = file_path.parent / new_name
    os.rename(file_path, new_file_path)

def process_directory(directory, replacements):
    # 遍历目录
    for file_path in Path(directory).rglob('*'):
        if file_path.is_file():
            replace_in_file(file_path, replacements)
            rename_file(file_path, replacements)

# 定义要替换的字符串
replacements = {
    'wlgc': 'zdm',
    'class':'wf',
    'r':'sore'
   
}

# 指定要遍历的目录
directory_path = Path.cwd() / 'test_ini'

# 调用函数处理目录
process_directory(directory_path, replacements)