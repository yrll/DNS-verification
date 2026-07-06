import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import os
from matplotlib.font_manager import FontProperties
from matplotlib.ticker import FuncFormatter

# 设置文件夹路径
file_path_Matsu = '/home/matsu/final_v1.1/symbolic_and_checking/matsu_zone_ct_mem_se.csv'
file_path_Groot = '/home/matsu/attributes.csv'

# 存储数据
at_data = []
lg_data = []
zone_values = []
construction_times = []
graph_building_times = []

# 读取 AT Construction 数据
df = pd.read_csv(file_path_Matsu)
if 'zone' in df.columns and 'symbolic execution and properties checking time (ms)' in df.columns:
    df = df.dropna(subset=['zone', 'symbolic execution and properties checking time (ms)'])
    df = df[df['symbolic execution and properties checking time (ms)'] != 0]
    df['symbolic execution and properties checking time (ms)'] = df['symbolic execution and properties checking time (ms)'] 
    at_data.append(df[['zone', 'symbolic execution and properties checking time (ms)']])

# 读取 LG Construction 数据
df = pd.read_csv(file_path_Groot)
if 'Domain' in df.columns and 'Property Checking (s)' in df.columns:
    df = df.dropna(subset=['Domain', 'Property Checking (s)'])
    df['Property Checking (s)'] = df['Property Checking (s)'] * 1000
    lg_data.append(df[['Domain', 'Property Checking (s)']])

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
merged_df['se time Ratio'] =  merged_df['Property Checking (s)'] / merged_df['symbolic execution and properties checking time (ms)']

# 过滤掉 ratio < 1 的数据并计算个数
count = (merged_df['se time Ratio'] < 1).sum()
print(f"Number of rows where ratio < 1: {count}")

# 获取比率最大的行
max_ratio_row = merged_df.loc[merged_df['se time Ratio'].idxmax()]

# 获取比率最小的行
min_ratio_row = merged_df.loc[merged_df['se time Ratio'].idxmin()]

# 打印比率最大的信息
print("### Maximum Ratio ###")
print(f"zone: {max_ratio_row['zone']}")
print(f"setime of Groot: {max_ratio_row['Property Checking (s)']} ")
print(f"setime of Matsu: {max_ratio_row['symbolic execution and properties checking time (ms)']} ")
print(f"se time Ratio: {max_ratio_row['se time Ratio']}")

# 打印比率最小的信息
print("\n### Minimum Ratio ###")
print(f"zone: {min_ratio_row['zone']}")
print(f"setime of Groot: {min_ratio_row['Property Checking (s)']} ")
print(f"setime of Matsu: {min_ratio_row['symbolic execution and properties checking time (ms)']} ")
print(f"se time Ratio: {min_ratio_row['se time Ratio']}")

# 获取比率小于1的数据
less_than_1_df = merged_df[merged_df['se time Ratio'] < 1].copy()

# 计算差异
less_than_1_df['difference'] = less_than_1_df['symbolic execution and properties checking time (ms)'] - less_than_1_df['Property Checking (s)']

# 打印出最大和最小的差异
max_difference_row = less_than_1_df.loc[less_than_1_df['difference'].idxmax()]
min_difference_row = less_than_1_df.loc[less_than_1_df['difference'].idxmin()]

print("\n### Maximum Difference ###")
print(f"zone: {max_difference_row['zone']}")
print(f"Difference: {max_difference_row['difference']}")
print(f"Symbolic Execution Time (Matsu): {max_difference_row['symbolic execution and properties checking time (ms)']}")
print(f"Property Checking Time (Groot): {max_difference_row['Property Checking (s)']}")

print("\n### Minimum Difference ###")
print(f"zone: {min_difference_row['zone']}")
print(f"Difference: {min_difference_row['difference']}")
print(f"Symbolic Execution Time (Matsu): {min_difference_row['symbolic execution and properties checking time (ms)']}")
print(f"Property Checking Time (Groot): {min_difference_row['Property Checking (s)']}")

# 保存 ratio < 1 的数据到 CSV 文件
output_file = '/home/matsu/final_v1.1/symbolic_and_checking/difference.csv'
less_than_1_df = less_than_1_df[['zone', 'Property Checking (s)', 'symbolic execution and properties checking time (ms)', 'se time Ratio', 'difference']]
less_than_1_df.to_csv(output_file, index=False)

print(f"Saved the data with ratio < 1 to {output_file}")

# 获取比率数据并排序
ratios = merged_df['se time Ratio'].dropna()
ratios_sorted = np.sort(ratios)
ratios_log = np.log10(ratios_sorted)

# 打印 quantile
quantiles = np.percentile(ratios_sorted, [90, 95, 99, 99.9])
print("\nRatio Quantiles (90%, 95%, 99%, 99.9%):")
print(f"90%: {quantiles[0]} ms")
print(f"95%: {quantiles[1]} ms")
print(f"99%: {quantiles[2]} ms")
print(f"99.9%: {quantiles[3]} ms")

# 绘制 CDF 图
plt.figure(figsize=(10, 8))
sns.kdeplot(ratios_log, cumulative=True, label='Symbolic Execution Time Ratio', color='#FF7F00', linewidth=10)

# 标记最大值
mark = ratios_sorted[-1]
max_ratio = ratios_log[-1]
min_ratio = ratios_log[0]
plt.annotate(
    f'Max: {mark:.2f}',
    xy=(max_ratio, 1.0),
    xytext=(max_ratio - 1.5 , 0.8),
    arrowprops=dict(facecolor='black', arrowstyle="->", linewidth=2),
    fontsize=26, 
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

plt.xlim(right=max_ratio)
plt.xlim(left=min_ratio)
plt.xlabel('CDF of Groot/Matsu Symbolic Execution Time Ratio', fontsize=22, fontweight='bold')
font = FontProperties(weight='bold', size=26)
plt.legend(prop=font, loc='lower right')
formatter = FuncFormatter(lambda x, _: f'$10^{{{x:.0f}}}$' if x > 0 else f'$10^{{{x:.0f}}}$')
ax.xaxis.set_major_formatter(formatter)
plt.tick_params(axis='both', labelsize=18)
plt.grid(True, linestyle='--', linewidth=1.5)

# 保存图像
plt.tight_layout()
plt.savefig('/home/matsu/final_draw/zone_symbolic_time/ratio/cdf_log_setime_ratio.png')

