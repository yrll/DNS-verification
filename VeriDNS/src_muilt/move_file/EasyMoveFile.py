import os
import shutil

def copy_subfolders(src_path, dst_path, num_folders):
    copied_count = 0  # 已复制的文件夹数量
    for root, dirs, files in os.walk(src_path, topdown=True):
        # 只考虑一级子文件夹
        for dir in dirs:
            src_folder_path = os.path.join(src_path, dir)
            dst_folder_path = os.path.join(dst_path, dir)
            
            # 如果目标文件夹已存在，则跳过
            if os.path.exists(dst_folder_path):
                continue
            
            # 复制文件夹
            shutil.copytree(src_folder_path, dst_folder_path)
            copied_count += 1
           
            # 检查是否达到阈值
            if copied_count >= num_folders:
                print(f"已达到阈值 {num_folders}，停止复制。")
                return
    print(f"文件夹{num_folders}已复制")
    
    
# 使用示例
base_path = r'E:\census\census'
destination_path = r'E:\census\census_100000_easy'
num_folders_to_copy = 100000

# 确保目标路径存在
if not os.path.exists(destination_path):
    os.makedirs(destination_path)

# 执行复制操作
copy_subfolders(base_path, destination_path, num_folders_to_copy)