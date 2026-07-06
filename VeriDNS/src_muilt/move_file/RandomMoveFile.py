import os
import random
import shutil


def random_copy_folders(src_path, dst_path, num_folders):
    # 确保目标路径存在
    if not os.path.exists(dst_path):
        os.makedirs(dst_path)

    # 获取所有一级子文件夹的列表
    folders = [name for name in os.listdir(src_path) if os.path.isdir(os.path.join(src_path, name))]

    # 随机选择num_folders数量的文件夹
    selected_folders = random.sample(folders, min(num_folders, len(folders)))

    # 复制选中的文件夹
    for folder_name in selected_folders:
        src_folder_path = os.path.join(src_path, folder_name)
        dst_folder_path = os.path.join(dst_path, folder_name)
        if os.path.exists(dst_folder_path):
            print(f"文件夹 {folder_name} 已经存在，跳过复制。")
            continue
        shutil.copytree(src_folder_path, dst_folder_path)
        print(f"文件夹 {folder_name} 已复制。")
    print("move over")

# 使用示例
base_path = r'/mnt/hdd1/allusers/bing_groot/sigcomm_data/census_100000_easy'
destination_path = r'/mnt/hdd1/allusers/bing_groot/sigcomm_data/census_10000_random'
num_folders_to_copy = 10000

# 执行复制操作
random_copy_folders(base_path, destination_path, num_folders_to_copy)
