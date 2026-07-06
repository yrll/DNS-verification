import pandas as pd
import numpy as np
import re

# 设置文件路径
file_path_rrnum = '/home/matsu/groot_bing/attributes_single_file.csv'
file_path_matsu_cttime = '/home/matsu/final_v1.1/construction_time_and_memory/matsu_zonefile_ct_mem.csv'
file_path_groot_cttime = '/home/matsu/groot_bing/attributes_single_file.csv'

# 存储数据
rr_data = []
mt_data = []
gr_data = []

# 读取 domain 和 total rrs 数据
df_rrnum = pd.read_csv(file_path_rrnum)
if 'Domain' in df_rrnum.columns and 'Total RRs' in df_rrnum.columns:
    df_rrnum = df_rrnum.dropna(subset=['Domain', 'Total RRs'])
    df_rrnum['Total RRs'] = df_rrnum['Total RRs']
    rr_data.append(df_rrnum[['Domain', 'Total RRs']])

# 读取 matsu construction time 数据
df_matsu_cttime = pd.read_csv(file_path_matsu_cttime)
if 'zone' in df_matsu_cttime.columns and 'construction time (ms)' in df_matsu_cttime.columns:
    df_matsu_cttime = df_matsu_cttime.dropna(subset=['zone', 'construction time (ms)'])
    df_matsu_cttime = df_matsu_cttime[df_matsu_cttime['construction time (ms)'] > 0]
    mt_data.append(df_matsu_cttime[['zone', 'construction time (ms)']])

# 读取 groot graph building 数据
df_groot_cttime = pd.read_csv(file_path_groot_cttime)
if 'Domain' in df_groot_cttime.columns and 'Graph building (s)' in df_groot_cttime.columns:
    df_groot_cttime = df_groot_cttime.dropna(subset=['Domain', 'Graph building (s)'])
    df_groot_cttime['Graph building (s)'] = df_groot_cttime['Graph building (s)'] * 1000  # 转换为ms
    gr_data.append(df_groot_cttime[['Domain', 'Graph building (s)']])

# 合并数据
rr_df = pd.concat(rr_data, ignore_index=True)
mt_df = pd.concat(mt_data, ignore_index=True)
gr_df = pd.concat(gr_data, ignore_index=True)

# 合并 rr_df 和 mt_df 按 Domain 匹配
merged_mt_df = pd.merge(rr_df, mt_df, left_on='Domain', right_on='zone', how='inner')

# 合并 merged_mt_df 和 gr_df 按 Domain 匹配
merged_df = pd.merge(merged_mt_df, gr_df, left_on='Domain', right_on='Domain', how='inner')

# 删除 zone 列（已包含在 Domain 列中）
merged_df = merged_df.drop(columns=['zone'])

# 筛选符合条件的 zone 数据
# 筛选符合条件的 zone 数据
filtered_df = merged_df[(merged_df['Graph building (s)'] > 1000) | 
                         (merged_df['Total RRs'] > 100000)]


# 提取符合条件的 zone 列并生成路径
zonefile_names = filtered_df['Domain']
path_list = []

for zone in zonefile_names:
    labels = zone.split('.')
    new_path = '/home/matsu/census/' + '.'.join(labels[-3:]) + '/' + zone + '.txt'
    
    # 去掉多余的点，确保路径正确
    new_path = new_path.replace('./', '/')
    
    path_list.append(new_path)

# 存储数据到 CSV 文件
zonefile_df = pd.DataFrame({
    'zonefile name': zonefile_names,
    'path': path_list
})

zonefile_df.to_csv('/home/matsu/final_v1.1/big_file_index/cttime_zonefile_level.csv', index=False)

print("处理完成，生成 zonefile.csv 文件。")
