import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import os
from matplotlib.font_manager import FontProperties
from matplotlib.ticker import FuncFormatter

# 设置文件夹路径
file_path_Matsu = '/home/matsu/final_v1.1/construction_time_and_memory/matsu_zone_ct_mem.csv'
file_path_Groot = '/home/matsu/attributes.csv'

mt_data = []
gr_data = []

# 读取mt cttime数据
df = pd.read_csv(file_path_Matsu)
if 'zone' in df.columns and 'construction time (ms)' in df.columns and 'metadata path' in df.columns:
    df = df.dropna(subset=['zone', 'construction time (ms)'])
    df['construction time (ms)'] = df['construction time (ms)']
    mt_data.append(df[['zone', 'metadata path', 'construction time (ms)']])

# 读取cttime数据
df = pd.read_csv(file_path_Groot)
if 'Domain' in df.columns and 'Graph building (s)' in df.columns:
    df = df.dropna(subset=['Domain', 'Graph building (s)'])
    df['Graph building (s)'] = df['Graph building (s)'] * 1000  # 转换为毫秒
    gr_data.append(df[['Domain', 'Graph building (s)']])

# 将 mt_data 和 gr_data 按 Domain 合并
mt_df = pd.concat(mt_data, ignore_index=True)
gr_df = pd.concat(gr_data, ignore_index=True)

merged_df = pd.merge(mt_df, gr_df, left_on='zone', right_on='Domain', how='inner')
# 删除无效的列 'zone'（它与 'Domain' 已经合并）
merged_df = merged_df.drop(columns=['zone'])

# 提取满足条件的行
filtered_df = merged_df[merged_df['construction time (ms)'] > merged_df['Graph building (s)']]

# 提取需要的列
filtered_df = filtered_df[['Domain', 'metadata path']]

# 修改列名
filtered_df.columns = ['zone name', 'path']

# 删除 'path' 列中的 "/metadata.json" 后缀
filtered_df['path'] = filtered_df['path'].str.replace('metadata.json', '', regex=False)

# 保存结果到新的 CSV 文件
output_path = '/home/matsu/final_v1.1/big_file_index/cttime_zone_level.csv'
filtered_df.to_csv(output_path, index=False)

print(f"Filtered data has been saved to {output_path}")
