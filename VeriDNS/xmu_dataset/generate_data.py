import os
from pathlib import Path
import shutil
import random
source_dir = Path.cwd() / "all_correct"
target_dir = Path.cwd() / "all_correct_10000"
epoch = 10000


if not target_dir.exists():
    target_dir.mkdir(parents=True)


for file_path in source_dir.iterdir():
    # 确保只有文件被复制（忽略目录）
    if file_path.is_file():
        # 定义目标文件路径
        target_file_path = target_dir / file_path.name
        
        # 复制文件
        shutil.copy(file_path, target_file_path)
        
for txt_file in target_dir.glob('*.txt'):
    domain = txt_file.name.replace('.txt', '').replace("-2","")
   
    # # 读取文件内容
    with open(txt_file, 'r', encoding='utf-8') as file:
        content = file.read()
        file.close()
    
    
    with open(txt_file, 'w') as f:
        f.write(content)
        # 随机生成100条记录
        for _ in range(epoch):
            d = random.sample(['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 
                'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 
                'x', 'y'], 8)
            d = ''.join(d) + '.' + domain
            ip = f'{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}'
            rr = f'{d:<25}IN    A    {ip}\n'
            f.write(rr)
        f.close()
        
print("Done!")