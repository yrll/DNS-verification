import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import os
from matplotlib.font_manager import FontProperties
from matplotlib.ticker import FuncFormatter

# 设置文件夹路径
file_path_Matsu = '/home/matsu/final_v1.1/construction_time_and_memory/matsu_zonefile_ct_mem.csv'
file_path_Groot = '/home/matsu/groot_bing/attributes_single_file.csv'

# 存储数据
at_data = []
lg_data = []
zone_values = []
construction_times = []
graph_building_times = []

# 读取 AT Construction 数据
df = pd.read_csv(file_path_Matsu)
if 'zone' in df.columns and 'construction time (ms)' in df.columns:
    df = df.dropna(subset=['zone', 'construction time (ms)'])
    df = df[df['construction time (ms)'] != 0]
    df['construction time (ms)'] = df['construction time (ms)'].astype(float)
    at_data.append(df[['zone', 'construction time (ms)']])

# 读取 LG Construction 数据
df = pd.read_csv(file_path_Groot)
if 'Domain' in df.columns :
    df = df.dropna(subset=['Domain', 'Graph building (s)'])
    df = df[df['Graph building (s)'] != 0]
    df['Graph building (s)'] = df['Graph building (s)'].astype(float) * 1000
    lg_data.append(df[['Domain', 'Graph building (s)']])

# 合并所有数据
at_df = pd.concat(at_data, ignore_index=True)
lg_df = pd.concat(lg_data, ignore_index=True)

# 根据 "zone" 列对齐数据
merged_df = pd.merge(
    at_df,
    lg_df,
    left_on='zone',
    right_on='Domain',
    how='inner'
)

# 计算比率
merged_df['cttime Ratio'] = merged_df['Graph building (s)'] / merged_df['construction time (ms)']

# 筛选出 ratio < 1 的数据
count = (merged_df['cttime Ratio'] < 1).sum()

# 打印结果
print(f"Number of rows where ratio < 1: {count}")

# 获取比率最大的行
max_ratio_row = merged_df.loc[merged_df['cttime Ratio'].idxmax()]

# 获取比率最小的行
min_ratio_row = merged_df.loc[merged_df['cttime Ratio'].idxmin()]

# 打印比率最大的信息
print("### Maximum Ratio ###")
print(f"Constructing ActionTrie for zone: {max_ratio_row['zone']}")
print(f"Groot: {max_ratio_row['Graph building (s)']} ")
print(f"Matsu: {max_ratio_row['construction time (ms)']} ")
print(f"cttime Ratio: {max_ratio_row['cttime Ratio']}")

# 打印比率最小的信息
print("\n### Minimum Ratio ###")
print(f"Constructing ActionTrie for zone: {min_ratio_row['zone']}")
print(f"Groot: {min_ratio_row['Graph building (s)']} ")
print(f"Matsu: {min_ratio_row['construction time (ms)']} ")
print(f"cttime Ratio: {min_ratio_row['cttime Ratio']}")

# 获取比率数据并排序
ratios = merged_df['cttime Ratio'].dropna()
ratios_sorted = np.sort(ratios)
quantiles = np.percentile(ratios_sorted, [90, 95, 99, 99.9])
ratios_sorted_log = np.log10(ratios_sorted)

# 打印结果
print("Ratio Quantiles (90%, 95%, 99%, 99.9%):")
print(f"90%: {quantiles[0]}")
print(f"95%: {quantiles[1]}")
print(f"99%: {quantiles[2]}")
print(f"99.9%: {quantiles[3]}")

# 绘制 CDF 图
plt.figure(figsize=(10, 8))
sns.kdeplot(ratios_sorted_log, cumulative=True, label='Construction Time Ratio', color='#FF7F00', linewidth=10)

# 标记最大值
mark = ratios_sorted[-1]
max_ratio = ratios_sorted_log[-1]
plt.annotate(
    f'Max: {mark:.2f}',
    xy=(max_ratio, 1.0),
    xytext=(max_ratio-1.8, 0.8),
    arrowprops=dict(facecolor='black', arrowstyle="->", linewidth=2),
    fontsize=30, 
    fontweight='bold',
    ha='center'
)

# 图表美化
ax = plt.gca()
ax.set_ylabel('')
ax.spines['top'].set_linewidth(2)
ax.spines['right'].set_linewidth(2)
ax.spines['bottom'].set_linewidth(2)
ax.spines['left'].set_linewidth(2)

plt.xlim(left=0, right=max_ratio)
plt.xlabel('CDF of Groot/Matsu Construction Time Ratio', fontsize=26, fontweight='bold')

font = FontProperties(weight='bold', size=30)
plt.legend(prop=font, loc='lower right')
# 设置 x 轴刻度为 10 的次方格式
formatter = FuncFormatter(lambda x, _: f'$10^{{{x:.0f}}}$' if x > 0 else f'$10^{{{x:.0f}}}$')
ax.xaxis.set_major_formatter(formatter)
plt.tick_params(axis='both', labelsize=18)
plt.grid(True, linestyle='--', linewidth=1.5)

# 保存图像
plt.tight_layout()
plt.savefig('/home/matsu/final_draw/zonefile_construction_time(valid bone)/ratio/cdf_ratio.pdf')

plt.show()
