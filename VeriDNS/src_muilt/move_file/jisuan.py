import os

def count_metadata_files(directory):
    metadata_count = 0
    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower() == 'metadata.json':  # 忽略文件名的大小写
                metadata_count += 1
    return metadata_count

if __name__ == '__main__':
    directory_path = r'D:\codewriting_graduate\me_python\my_paper_sigcomm\test_census'  # 替换为你要统计的文件夹路径
    total_metadata_files = count_metadata_files(directory_path)
    print(f"Total 'metadata.json' files found: {total_metadata_files}")