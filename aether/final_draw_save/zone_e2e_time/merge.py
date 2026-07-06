import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.ticker import FuncFormatter

# 设置文件路径
file_path_Matsu_ct = '/home/matsu/final_v1.1/Matsu_cttime/Matsu_cttime.csv'
file_path_Matsu_se = '/home/matsu/final_v1.1/symbolic_and_checking/matsu_zone_ct_mem_se.csv'


# 存储数据
mt_data = []
gr_data = []
re_data = []

# 读取 Matsu 的建构时间数据
df = pd.read_csv(file_path_Matsu_ct)
if 'zone' in df.columns and 'construction time (ms)' in df.columns:
    df = df.dropna(subset=['zone', 'construction time (ms)'])
    df['construction time (ms)'] = df['construction time (ms)']
    mt_data.append(df[['zone', 'construction time (ms)']])

# 读取 Matsu 的符号执行时间数据
df = pd.read_csv(file_path_Matsu_se)
if 'zone' in df.columns and 'symbolic execution and properties checking time (ms)' in df.columns:
    df = df.dropna(subset=['zone', 'symbolic execution and properties checking time (ms)'])
    df['symbolic execution and properties checking time (ms)'] = df['symbolic execution and properties checking time (ms)']
    gr_data.append(df[['zone', 'symbolic execution and properties checking time (ms)']])

# 合并所有数据
mt_df = pd.concat(mt_data, ignore_index=True)
gr_df = pd.concat(gr_data, ignore_index=True)

merge_df = pd.merge(mt_df, gr_df, on='zone', how='inner')

print(f"Rows after merge: {merge_df.shape[0]}")
print(merge_df.head())


# 计算 Matsu 和 Groot 的端到端时间
merge_df['e2etime'] = merge_df['construction time (ms)'] + merge_df['symbolic execution and properties checking time (ms)']

less_than_1_df = merge_df.copy()

output_file = '/home/matsu/final_v1.1/end_to_end_time/difference.csv'
less_than_1_df = less_than_1_df[['zone', 'e2etime']]
less_than_1_df.to_csv(output_file, index=False)

print(f"Saved to {output_file}")