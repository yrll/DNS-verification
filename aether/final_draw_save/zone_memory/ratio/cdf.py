import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import os
from matplotlib.font_manager import FontProperties
from matplotlib.ticker import FuncFormatter
from matplotlib.ticker import MaxNLocator


# 设置文件夹路径
folder_path_Matsu = '/home/matsu/final_v1.1/construction_time_and_memory/matsu_zone_ct_mem.csv'
folder_path_Groot = '/home/matsu/final_v1.1/construction_time_and_memory/groot_zone_ct_mem.csv'

# 存储数据
at_data = []
lg_data = []
zone_values = []

# 读取 AT Construction 数据
df = pd.read_csv(folder_path_Matsu)
if 'zone' in df.columns and 'memory lower bound (bytes)' in df.columns:
    df = df.dropna(subset=['zone', 'memory lower bound (bytes)'])
    df = df[df['memory lower bound (bytes)'] != 0]
    df['memory lower bound (bytes)'] = df['memory lower bound (bytes)'] / (1024*1024)
    at_data.append(df[['zone', 'memory lower bound (bytes)']])

# 读取 LG Construction 数据
df = pd.read_csv(folder_path_Groot)
if 'zone' in df.columns and 'full lec memory (bytes)' in df.columns:
    df = df.dropna(subset=['zone', 'full lec memory (bytes)'])
    df['full lec memory (bytes)'] = df['full lec memory (bytes)'] / (1024*1024)
    lg_data.append(df[['zone', 'full lec memory (bytes)']])

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
merged_df['memory Ratio'] =  merged_df['full lec memory (bytes)'] / merged_df['memory lower bound (bytes)']

# 筛选出 ratio < 1 的数据
count = (merged_df['memory Ratio'] < 1).sum()

# 打印结果
print(f"Number of rows where ratio < 1: {count}")

# # 获取比率最大的行
# max_ratio_row = merged_df.loc[merged_df['memory Ratio'].idxmax()]

# # 获取比率最小的行
# min_ratio_row = merged_df.loc[merged_df['memory Ratio'].idxmin()]

# # 打印比率最大的信息
# print("### Maximum Ratio ###")
# print(f"zone: {max_ratio_row['zone']}")
# print(f"memory size of Groot: {max_ratio_row['full lec memory (bytes)']} ")
# print(f"memory size of Matsu: {max_ratio_row['memory upper bound (bytes)']} ")
# print(f"memory Ratio: {max_ratio_row['memory Ratio']}")

# # 打印比率最小的信息
# print("\n### Minimum Ratio ###")
# print(f"zone: {min_ratio_row['zone']}")
# print(f"memory size of Groot: {min_ratio_row['full lec memory (bytes)']} ")
# print(f"memory size of Matsu: {min_ratio_row['memory upper bound (bytes)']} ")
# print(f"memory Ratio: {min_ratio_row['memory Ratio']}")

# 获取比率数据并排序
ratios = merged_df['memory Ratio'].dropna()
ratios_sorted = np.sort(ratios)

# # 求quantile
# quantiles = np.percentile(ratios_sorted, [90, 95, 99, 99.9])

# # 打印结果
# print("Ratio Quantiles (90%, 95%, 99%, 99.9%):")
# print(f"90%: {quantiles[0]}")
# print(f"95%: {quantiles[1]}")
# print(f"99%: {quantiles[2]}")
# print(f"99.9%: {quantiles[3]}")

# # 取对
# ratios_sorted_log = np.log10(np.array(ratios_sorted))

# 绘制 CDF 图
plt.figure(figsize=(10, 8))
sns.kdeplot(ratios_sorted, cumulative=True, label='Memory Size Ratio',color='#FF7F00',linewidth=10)

# 标记最大值
max_ratio = ratios_sorted[-1]
min_ratio = ratios_sorted[0]
# mark = ratios_sorted[-1]
plt.annotate(
    f'Max: {max_ratio:.2f}',
    xy=(max_ratio, 1.0),
    xytext=(max_ratio - 60, 0.8),
    arrowprops=dict(facecolor='black', arrowstyle="->", linewidth=2),
    fontsize=34, 
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
plt.xlabel('CDF of Groot/Matsu Memory Size Ratio', fontsize=30, fontweight='bold')

font = FontProperties(weight='bold', size=30)
plt.legend(prop=font, loc='lower right')

# # 设置X轴的主要定位器以限制刻度数量
# ax.xaxis.set_major_locator(MaxNLocator(4))  # 设置为4个主要刻度

# # 定义格式化函数
# formatter = FuncFormatter(lambda x, _: f'$10^{{{x:.0f}}}$')
# ax.xaxis.set_major_formatter(formatter)  # 应用格式化器到X轴
# formatter = FuncFormatter(lambda x, _: f'$10^{{{x:.0f}}}$' if x > 0 else f'$10^{{{x:.0f}}}$')

plt.tick_params(axis='both', labelsize=18)
plt.grid(True, linestyle='--', linewidth=1.5)

# 保存图像
plt.tight_layout()
plt.savefig('/home/matsu/final_draw/zone_memory/ratio/cdf_lower_memory_ratio.png')

plt.show()
