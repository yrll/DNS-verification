import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import os
from matplotlib.font_manager import FontProperties

# 设置文件夹路径
folder_path_AT_time = '/home/matsu/final_v1.1/construction_time_and_memory/matsu_zone_ct_mem.csv'
folder_path_AT_timeG = '/home/matsu/final_v1.1/construction_time_and_memory/groot_zone_ct_mem.csv'

# 存储数据
at_data = []
lg_data = []
zone_values = []

# 读取 AT Construction 数据
df = pd.read_csv(folder_path_AT_time)
if 'zone' in df.columns and 'construction time (ms)' in df.columns:
    df = df.dropna(subset=['zone', 'construction time (ms)'])
    df = df[df['construction time (ms)'] != 0]
    df['construction time (ms)'] = df['construction time (ms)']
    at_data.append(df[['zone', 'construction time (ms)']])

# 读取 LG Construction 数据
df = pd.read_csv(folder_path_AT_timeG)
if 'zone' in df.columns and 'total time (ms)' in df.columns:
    df = df.dropna(subset=['zone', 'total time (ms)'])
    df['total time (ms)'] = df['total time (ms)'] 
    lg_data.append(df[['zone', 'total time (ms)']])

# 合并所有数据
at_df = pd.concat(at_data, ignore_index=True)
lg_df = pd.concat(lg_data, ignore_index=True)


## 根据 "zone" 列对齐数据
merged_df = pd.merge(
    at_df,
    lg_df,
    left_on='zone',
    right_on='zone',
    how='inner'
)

# 计算比率
merged_df['ct time Ratio'] =  merged_df['total time (ms)'] / merged_df['construction time (ms)']

# # 获取比率最大的行
# max_ratio_row = merged_df.loc[merged_df['ct time Ratio'].idxmax()]

# # 获取比率最小的行
# min_ratio_row = merged_df.loc[merged_df['ct time Ratio'].idxmin()]

# # 打印比率最大的信息
# print("### Maximum Ratio ###")
# print(f"zone: {max_ratio_row['zone']}")
# print(f"cttime of Groot: {max_ratio_row['total time (ms)']} ")
# print(f"cttime of Matsu: {max_ratio_row['construction time (ms)']} ")
# print(f"ct time Ratio: {max_ratio_row['ct time Ratio']}")

# # 打印比率最小的信息
# print("\n### Minimum Ratio ###")
# print(f"zone: {min_ratio_row['zone']}")
# print(f"cttime of Groot: {min_ratio_row['total time (ms)']} ")
# print(f"cttime of Matsu: {min_ratio_row['construction time (ms)']} ")
# print(f"ct time Ratio: {min_ratio_row['ct time Ratio']}")

# 获取比率数据并排序
ratios = merged_df['ct time Ratio'].dropna()
ratios_sorted = np.sort(ratios)

# 计算99%分位数
quantile_99 = np.percentile(ratios_sorted, 99)
quantile_95 = np.percentile(ratios_sorted, 95)

# 绘制 CDF 图
plt.figure(figsize=(12, 6))
sns.kdeplot(ratios_sorted, cumulative=True, label='Construction Time Ratio', color='#FF7F00', linewidth=8)

# 使用箭头标注分位数
plt.annotate(
    f'95% Quantile: {quantile_95:.2f}',
    xy=(quantile_95, 0.99),  # 箭头指向位置
    xytext=(quantile_95 + 4, 0.7),  # 注释文本位置
    arrowprops=dict(facecolor='blue', arrowstyle="->", linewidth=2),
    fontsize=26,
    fontweight='bold',
    ha='center'
)
plt.annotate(
    f'99% Quantile: {quantile_99:.2f}',
    xy=(quantile_99, 0.99),  # 箭头指向位置
    xytext=(quantile_99 + 5, 0.8),  # 注释文本位置
    arrowprops=dict(facecolor='blue', arrowstyle="->", linewidth=2),
    fontsize=26,
    fontweight='bold',
    ha='center'
)



# 标记最大值
max_ratio = ratios_sorted[-1]
plt.annotate(
    f'Max: {max_ratio:.2f}',
    xy=(max_ratio, 1.0),
    xytext=(max_ratio - 2.5, 0.8),
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
plt.xlabel('CDF of Groot/Matsu Construction Time Ratio', fontsize=24, fontweight='bold')

font = FontProperties(weight='bold', size=26)
plt.legend(prop=font, loc='lower right')
plt.tick_params(axis='both', labelsize=18)
plt.grid(True, linestyle='--', linewidth=1.5)

# 保存图像
plt.tight_layout()
plt.savefig('/home/matsu/final_draw/construction_time/ratio/cdf_cttime_with_quantile_ratio.png')

plt.show()
