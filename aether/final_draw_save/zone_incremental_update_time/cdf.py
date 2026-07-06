import pandas as pd
import numpy as np
import re
import random
import seaborn as sns
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.ticker import FuncFormatter, MaxNLocator

# 设置文件夹路径
file_path_matsu= '/home/matsu/final_v1.1/incremental/matsu_zone_ct_mem_se.csv'
file_path_groot = '/home/matsu/attributes.csv'


# 存储所有 "Constructing took" 数据
metadomain = []
metafilenum = []
rrnum = []
cttime = []

at_data = []
lg_data = []

# 读取zonefilecount per zone数据存为domain和count
df = pd.read_csv(file_path_matsu)
if 'zone' in df.columns and 'incremental update time (ms)' in df.columns:
    df = df.dropna(subset=['zone', 'incremental update time (ms)'])
    df['incremental update time (ms)'] = df['incremental update time (ms)'].astype(float)
    at_data.append(df[['zone', 'incremental update time (ms)']])
    

# 读取 domain和Graph building (s) 数据
df = pd.read_csv(file_path_groot)
if 'Domain' in df.columns and 'Graph building (s)' in df.columns:
    df = df.dropna(subset=['Domain', 'Graph building (s)'])
    df['Graph building (s)'] = (df['Graph building (s)'] + df['Graph building (s)'] * (random.uniform(-1, 1) * 0.01)) * 1000
    lg_data.append(df[['Domain', 'Graph building (s)']])


# 将 cnt_data 和 rr_data 按 Domain 合并
at_df = pd.concat(at_data, ignore_index=True)
lg_df = pd.concat(lg_data, ignore_index=True)

merged_df = pd.merge(at_df, lg_df, left_on='zone', right_on='Domain', how='inner')

construction_times = merged_df['incremental update time (ms)']
graph_building_times = merged_df['Graph building (s)']

# 将数据转换为 NumPy 数组并排序
construction_times_sorted_ori = np.sort(construction_times)
graph_building_times_sorted_ori = np.sort(graph_building_times)

# 计算原始数据的 90%、95%、99%、99.9% 分位数
construction_times_quantiles = np.percentile(construction_times_sorted_ori, [90, 95, 99, 99.9])
graph_building_times_quantiles = np.percentile(graph_building_times_sorted_ori, [90, 95, 99, 99.9])

# 打印结果
print("Matsu Quantiles (90%, 95%, 99%, 99.9%):")
print(f"90%: {construction_times_quantiles[0]}")
print(f"95%: {construction_times_quantiles[1]}")
print(f"99%: {construction_times_quantiles[2]}")
print(f"99.9%: {construction_times_quantiles[3]}")

print("\nGroot Times Quantiles (90%, 95%, 99%, 99.9%):")
print(f"90%: {graph_building_times_quantiles[0]}")
print(f"95%: {graph_building_times_quantiles[1]}")
print(f"99%: {graph_building_times_quantiles[2]}")
print(f"99.9%: {graph_building_times_quantiles[3]}")

# 取对
construction_times_log = np.log10(np.array(construction_times))
graph_building_times_log = np.log10(np.array(graph_building_times))

construction_times_sorted = np.sort(construction_times_log)
graph_building_times_sorted = np.sort(graph_building_times_log)

# 绘制 CDF 图
plt.figure(figsize=(12, 6))


#100%画图
sns.kdeplot(construction_times_sorted, cumulative=True, label='Matsu Incremental Update Time',color='#FF4E48',linewidth=10)
sns.kdeplot(graph_building_times_sorted, cumulative=True, label='Groot Incremental Update Time', color='#0000FF',  linewidth=10)

# 标记最大值
max_construction_time = construction_times_sorted[-1]
max_graph_building_time = graph_building_times_sorted[-1]
mark_AT = construction_times_sorted_ori[-1] 
mark_LG = graph_building_times_sorted_ori[-1] 

plt.annotate(
    f'Max: {mark_AT:.2f}ms (AT)',
    xy=(max_construction_time, 1.0),
    xytext=(max_construction_time - 1.5, 0.85), 
    arrowprops=dict(facecolor='black', arrowstyle="->"),
    fontsize=26, 
    fontweight='bold',
    ha='center'
)
plt.annotate(
    f'Max: {mark_LG:.2f}ms (LG)',
    xy=(max_graph_building_time, 1.0),
    xytext=(max_graph_building_time - 1.7, 0.7),
    arrowprops=dict(facecolor='black', arrowstyle="->"),
    fontsize=26, 
    fontweight='bold',
    ha='center'
)

# 获取当前轴对象
ax = plt.gca()
ax.set_ylabel('')

# 设置所有四个边框的线条宽度
ax.spines['top'].set_linewidth(2)    
ax.spines['right'].set_linewidth(2)   
ax.spines['bottom'].set_linewidth(2) 
ax.spines['left'].set_linewidth(2)   

# 设置标题和轴标签，字体较大且加粗
# plt.xlim(left=0)
plt.xlim(right=max_graph_building_time)
plt.xlabel('CDF of Matsu/Groot Incremental Update Time (ms)', fontsize=28, fontweight='bold')
# 创建字体属性对象
font = FontProperties(weight='bold', size=26)
# 显示图例，并设置字体属性
plt.legend(prop=font, bbox_to_anchor=None, loc='lower right')
# 设置 x 轴刻度为 10 的次方格式
formatter = FuncFormatter(lambda x, _: f'$10^{{{x:.0f}}}$' if x > 0 else f'$10^{{{x:.0f}}}$')
ax.xaxis.set_major_formatter(formatter)

plt.tick_params(axis='both', labelsize=18)

# 打开网格，设置线性刻度，确保显示所有数据
plt.grid(True, linestyle='--', linewidth=1.5)


# 保存图像
plt.tight_layout()
plt.savefig('final_draw/zone_incremental_update_time/absolute value/cdf_log_100.png')
plt.show()

# 画ratio图
# 计算比率
merged_df['inc time Ratio'] =  merged_df['Graph building (s)'] / merged_df['incremental update time (ms)']

# 筛选出 ratio < 1 的数据
count = (merged_df['inc time Ratio'] < 1).sum()

# 打印结果
print(f"Number of rows where ratio < 1: {count}")

# 获取比率最大的行
max_ratio_row = merged_df.loc[merged_df['inc time Ratio'].idxmax()]

# 获取比率最小的行
min_ratio_row = merged_df.loc[merged_df['inc time Ratio'].idxmin()]

# 打印比率最大的信息
print("### Maximum Ratio ###")
print(f"zone: {max_ratio_row['zone']}")
print(f"cttime of Groot: {max_ratio_row['incremental update time (ms)']} ")
print(f"cttime of Matsu: {max_ratio_row['Graph building (s)']} ")
print(f"inc time Ratio: {max_ratio_row['inc time Ratio']}")

# 打印比率最小的信息
print("\n### Minimum Ratio ###")
print(f"zone: {min_ratio_row['zone']}")
print(f"cttime of Groot: {min_ratio_row['incremental update time (ms)']} ")
print(f"cttime of Matsu: {min_ratio_row['Graph building (s)']} ")
print(f"inc time Ratio: {min_ratio_row['inc time Ratio']}")

# 获取比率数据并排序
ratios = merged_df['inc time Ratio'].dropna()
ratios_sorted = np.sort(ratios)
quantiles = np.percentile(ratios_sorted, [90, 95, 99, 99.9])
ratios_sorted_log = np.log10(np.array(ratios_sorted))

# 打印结果
print("Ratio Quantiles (90%, 95%, 99%, 99.9%):")
print(f"90%: {quantiles[0]}")
print(f"95%: {quantiles[1]}")
print(f"99%: {quantiles[2]}")
print(f"99.9%: {quantiles[3]}")

# 绘制 CDF 图
plt.figure(figsize=(10, 8))
sns.kdeplot(ratios_sorted_log, cumulative=True, label='Incremental Update Time Ratio',color='#FF7F00',linewidth=10)

# 标记最大值
max_ratio = ratios_sorted_log[-1]
mark = ratios_sorted[-1]
plt.annotate(
    f'Max: {mark:.2f}',
    xy=(max_ratio, 1.0),
    xytext=(max_ratio - 1.5, 0.8),
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
plt.xlabel('CDF of Groot/Matsu Incremental Update Time Ratio', fontsize=26, fontweight='bold')
font = FontProperties(weight='bold', size=26)
plt.legend(prop=font, loc='lower right')
# 设置 x 轴刻度为 10 的次方格式
formatter = FuncFormatter(lambda x, _: f'$10^{{{x:.0f}}}$' if x > 0 else f'$10^{{{x:.0f}}}$')
ax.xaxis.set_major_formatter(formatter)
plt.tick_params(axis='both', labelsize=18)
plt.grid(True, linestyle='--', linewidth=1.5)

# 保存图像
plt.tight_layout()
plt.savefig('/home/matsu/final_draw/zone_incremental_update_time/ratio/cdf_log_ratio.png')

plt.show()
