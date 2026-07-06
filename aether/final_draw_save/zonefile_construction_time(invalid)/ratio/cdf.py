import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import os
from matplotlib.font_manager import FontProperties

# 设置文件夹路径
folder_path_AT_time = '/home/matsu/final_v1.1/LEC_num/Matsu_LEC'
folder_path_AT_timeG = '/home/matsu/final_v1.1/LEC_num/Groot_EC'

# 存储数据
at_data = []
lg_data = []
zone_values = []

# 读取 AT Construction 数据
for filename in os.listdir(folder_path_AT_time):
    if filename.endswith('.csv'):
        file_path = os.path.join(folder_path_AT_time, filename)
        df = pd.read_csv(file_path)
        if 'Constructing ActionTrie for Zone' in df.columns and 'Constructing Took' in df.columns:
            df = df.dropna(subset=['Constructing ActionTrie for Zone', 'Constructing Took'])
            df = df[df['Constructing Took'] != 0]
            df['Constructing Took'] = df['Constructing Took'].str.replace('ms', '').astype(float)
            at_data.append(df[['Constructing ActionTrie for Zone', 'Constructing Took']])

# 读取 LG Construction 数据
for filename in os.listdir(folder_path_AT_timeG):
    if filename.endswith('.csv'):
        file_path = os.path.join(folder_path_AT_timeG, filename)
        df = pd.read_csv(file_path)
        if 'Building label graph for zone' in df.columns :
            df = df.dropna(subset=['Building label graph for zone', 'Building label graph took','Generating LECs took'])
            df['Building label graph took'] = df['Building label graph took'].str.replace('ms', '').astype(float)
            df['Generating LECs took'] = df['Generating LECs took'].str.replace('ms', '').astype(float)
            df['Total Time'] = df['Building label graph took'] + df['Generating LECs took']
            lg_data.append(df[['Building label graph for zone', 'Total Time']])

# 合并所有数据
at_df = pd.concat(at_data, ignore_index=True)
lg_df = pd.concat(lg_data, ignore_index=True)

# 根据 "zone" 列对齐数据
merged_df = pd.merge(
    at_df,
    lg_df,
    left_on='Constructing ActionTrie for Zone',
    right_on='Building label graph for zone',
    how='inner'
)

# 过滤掉 Total Time 中的零值
merged_df = merged_df[merged_df['Total Time'] != 0]

# 计算比率
merged_df['cttime Ratio'] = merged_df['Total Time'] / merged_df['Constructing Took']

# 筛选出 ratio < 1 的数据
count = (merged_df['cttime Ratio'] < 1).sum()

# 打印结果
print(f"Number of rows where ratio < 1: {count}")

# # 获取比率最大的行
# max_ratio_row = merged_df.loc[merged_df['cttime Ratio'].idxmax()]

# # 获取比率最小的行
# min_ratio_row = merged_df.loc[merged_df['cttime Ratio'].idxmin()]

# # 打印比率最大的信息
# print("### Maximum Ratio ###")
# print(f"Constructing ActionTrie for zone: {max_ratio_row['Constructing ActionTrie for Zone']}")
# print(f"Groot: {max_ratio_row['Total Time']} ")
# print(f"Matsu: {max_ratio_row['Constructing Took']} ")
# print(f"cttime Ratio: {max_ratio_row['cttime Ratio']}")

# # 打印比率最小的信息
# print("\n### Minimum Ratio ###")
# print(f"Constructing ActionTrie for zone: {min_ratio_row['Constructing ActionTrie for Zone']}")
# print(f"Groot: {min_ratio_row['Total Time']} ")
# print(f"Matsu: {min_ratio_row['Constructing Took']} ")
# print(f"cttime Ratio: {min_ratio_row['cttime Ratio']}")

# # 获取比率数据并排序
# ratios = merged_df['cttime Ratio'].dropna()
# ratios_sorted = np.sort(ratios)
# quantiles = np.percentile(ratios_sorted, [90, 95, 99, 99.9])

# # 打印结果
# print("Ratio Quantiles (90%, 95%, 99%, 99.9%):")
# print(f"90%: {quantiles[0]}")
# print(f"95%: {quantiles[1]}")
# print(f"99%: {quantiles[2]}")
# print(f"99.9%: {quantiles[3]}")

# # 绘制 CDF 图
# plt.figure(figsize=(12, 6))
# sns.kdeplot(ratios_sorted, cumulative=True, label='Construction Time Ratio', color='#FF7F00', linewidth=8)

# # 标记最大值
# max_ratio = ratios_sorted[-1]
# plt.annotate(
#     f'Max: {max_ratio:.2f}',
#     xy=(max_ratio, 1.0),
#     xytext=(max_ratio-2, 0.8),
#     arrowprops=dict(facecolor='black', arrowstyle="->", linewidth=2),
#     fontsize=26, 
#     fontweight='bold',
#     ha='center'
# )

# # 图表美化
# ax = plt.gca()
# ax.set_ylabel('')
# ax.spines['top'].set_linewidth(2)
# ax.spines['right'].set_linewidth(2)
# ax.spines['bottom'].set_linewidth(2)
# ax.spines['left'].set_linewidth(2)

# plt.xlim(left=0, right=max_ratio)
# plt.xlabel('CDF of Groot/Matsu Construction Time Ratio', fontsize=30, fontweight='bold')

# font = FontProperties(weight='bold', size=26)
# plt.legend(prop=font, loc='lower right')
# plt.tick_params(axis='both', labelsize=18)
# plt.grid(True, linestyle='--', linewidth=1.5)

# # 保存图像
# plt.tight_layout()
# plt.savefig('/home/matsu/final_draw/zonefile_construction_time/ratio/cdf_ratio.png')

# plt.show()
