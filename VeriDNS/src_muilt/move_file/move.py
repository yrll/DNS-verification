import os
import shutil


def move_subfolders_to_root(root_dir, target_dir):
    # 确保目标目录存在
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)

    # 获取一级子目录列表
    for root, dirs, files in os.walk(root_dir):
        for dir_name in dirs:
            # 形成一级子目录路径
            first_level_dir = os.path.join(root, dir_name)

            # 获取一级子目录下的所有二级子目录
            for sub_root, sub_dirs, sub_files in os.walk(first_level_dir):
                for sub_dir_name in sub_dirs:
                    # 形成二级子目录路径
                    second_level_dir = os.path.join(sub_root, sub_dir_name)

                    # 形成目标路径，将二级子目录复制到目标目录
                    target_sub_dir = os.path.join(target_dir, sub_dir_name)
                    shutil.copytree(second_level_dir, target_sub_dir)

                # 处理完所有二级子目录后，跳出循环
                break

        # 处理完所有一级子目录后，跳出循环
        break


# 示例用法
root_directory = r'D:\codewriting_graduate\me_python\my_paper_sigcomm\test_census_2'
target_directory = r'D:\codewriting_graduate\me_python\my_paper_sigcomm\test_census_3'  # 替换为你的根目录路径
move_subfolders_to_root(root_directory, target_directory)
