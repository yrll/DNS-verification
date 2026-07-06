from pathlib import Path
import shutil
dir_12 =["com.",
    "xmu.com.",
    "lzu.com.",
    "arch.tju.com.",
    "hyxt.whu.com.",
    "software.nju.com.",
    "math.pku.com.",
    "www.cqu.com.",
    "www.shu.com.",
    "xben.com.",
    "r.class.wlgc.com.-2",
    "sore.wf.zdm.com.",
    "hlt.ftw.com."]

dir_13 =["www.xmu.com.",
    "www.lzu.com.",
    "tju.com.",
    "whu.com.",
    "law.nju.com.",
    "hist.pku.com.",
    "sci.cqu.com.",
    "ai.shu.com.",
    "child.xben.com.",
    "wlgc.com.",
    "sore.wf.zdm.com.-2",
    "wc.hlt.ftw.com."]


dir_14 = [
    "informatics.xmu.com.",
    "xw.lzu.com.",
    "www.tju.com.",
    "www.whu.com.",
    "nju.com.",
    "pku.com.",
    "cse.cqu.com.",
    "sociology.shu.com.",
    "r.child.xben.com.",
    "class.wlgc.com.",
    "zdm.com.",
    "wc.hlt.ftw.com.-2"
]

dir_15 = [
    "sm.xmu.com.",
    "zheshexi.lzu.com.",
    "science.tju.com.",
    "pharm.whu.com.",
    "www.nju.com.",
    "www.pku.com.",
    "cqu.com.",
    "shu.com.",
    "r.child.xben.com.-2",
    "r.class.wlgc.com.",
    "wf.zdm.com.",
    "ftw.com."
]


cwd = Path.cwd()
domain_lists = [dir_12, dir_13, dir_14, dir_15]
folder_names = ['12', '13', '14', '15']
all_correct_path = cwd / 'all_correct_10000'

for folder in folder_names:
    dir_path = cwd / folder
    if not dir_path.exists():
        dir_path.mkdir(parents=True)

if not all_correct_path.exists():
    print('The all_correct directory does not exist.')
else:
    # 遍历每个文件夹名称和域名列表
    for folder_name, domain_list in zip(folder_names, domain_lists):
        # 创建对应的文件夹路径
        target_folder = cwd / folder_name
        
        # 遍历域名列表
        for domain in domain_list:
            # 从all_correct文件夹中获取源文件路径
            domain_path = all_correct_path / f"{domain}.txt"
            
            # 检查文件是否存在
            if not domain_path.exists():
                print(f"The file {domain_path.name} does not exist in all_correct and will be skipped.")
                continue
            
            # 目标文件路径
            target_path = target_folder / domain_path.name
           
            # 复制文件
            shutil.copy(domain_path, target_path)

    print("Files have been copied to the respective folders.")