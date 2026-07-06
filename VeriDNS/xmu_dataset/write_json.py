from pathlib import Path
import json

# 获取当前工作目录的Path对象
cwd = Path.cwd()
dir_path = cwd / '15'
# 存放metadata.json的文件路径
metadata_file = dir_path / 'metadata.json'

# 读取现有的metadata.json文件内容
try:
    with open(metadata_file) as f:
        metadata = json.load(f)
except FileNotFoundError:
    metadata = {"ZoneFiles": []}

# 构造ZoneFiles列表
zone_files = []
for txt_file in dir_path.glob('*.txt'):
    name_server = txt_file.stem  # 获取文件名（不包含后缀）
    origin = name_server
    level = name_server.count('.')
    if level == 4 and name_server.endswith("-2"):
        origin = name_server[:-2]
        name_server = "ns2." + origin
    else:
        name_server = "ns1." + origin
        
    zone_file = {
        "FileName": txt_file.name,
        "NameServer": name_server,
        "Origin":origin
    }
    zone_files.append(zone_file)

# 更新metadata字典
metadata["ZoneFiles"] = zone_files

# 将更新后的metadata写回到metadata.json文件
with open(metadata_file, 'w') as f:
    json.dump(metadata, f, indent=4)

print(f'Updated {metadata_file} with the following content:')
# print(json.dumps(metadata, indent=4))