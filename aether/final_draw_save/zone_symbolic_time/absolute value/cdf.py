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
re_data = []
zone_values = []
construction_times = []
graph_building_times = []

# 读取 AT se 数据

df = pd.read_csv(file_path_Matsu)
if 'zone' in df.columns and 'symbolic execution and properties checking time (ms)' in df.columns:
    df = df.dropna(subset=['zone', 'symbolic execution and properties checking time (ms)'])
    df = df[df['symbolic execution and properties checking time (ms)'] != 0]
    df['symbolic execution and properties checking time (ms)'] = df['symbolic execution and properties checking time (ms)'] 
    at_data.append(df[['zone', 'symbolic execution and properties checking time (ms)']])

# 读取 LG se 数据

df = pd.read_csv(file_path_Groot)
if 'Domain' in df.columns and 'Property Checking (s)' in df.columns:
    df = df.dropna(subset=['Domain', 'Property Checking (s)'])
    df['Property Checking (s)'] = df['Property Checking (s)']  * 1000
    lg_data.append(df[['Domain', 'Property Checking (s)']])



# 合并所有数据
at_df = pd.concat(at_data, ignore_index=True)
lg_df = pd.concat(lg_data, ignore_index=True)


merged_df = pd.merge(at_df, lg_df, left_on='zone', right_on='Domain', how='inner')

construction_times = merged_df['symbolic execution and properties checking time (ms)']
graph_building_times = merged_df['Property Checking (s)']


# 获取最大的行
max_matsu_row = merged_df.loc[merged_df['symbolic execution and properties checking time (ms)'].idxmax()]
max_groot_row = merged_df.loc[merged_df['Property Checking (s)'].idxmax()]

# 打印最大的信息
print("### Max Matsu###")
print(f"zone: {max_matsu_row['zone']}")
print(f"setime of Matsu: {max_matsu_row['symbolic execution and properties checking time (ms)']} ms")

print("\n### Max Groot###")
print(f"zone: {max_groot_row['zone']}")
print(f"setime of Groot: {max_groot_row['Property Checking (s)']} ms")

# 获取最小的行
min_matsu_row = merged_df.loc[merged_df['symbolic execution and properties checking time (ms)'].idxmin()]
min_groot_row = merged_df.loc[merged_df['Property Checking (s)'].idxmin()]

# 打印最小的信息
print("### Min Matsu###")
print(f"zone: {min_matsu_row['zone']}")
print(f"setime of Matsu: {min_matsu_row['symbolic execution and properties checking time (ms)']} ms")

print("\n### Min Groot###")
print(f"zone: {min_groot_row['zone']}")
print(f"setime of Groot: {min_groot_row['Property Checking (s)']} ms")


# 将数据转换为 NumPy 数组并排序
construction_times_sorted_ori = np.sort(construction_times)
graph_building_times_sorted_ori = np.sort(graph_building_times)

# 计算原始数据的 90%、95%、99%、99.9% 分位数
construction_times_quantiles = np.percentile(construction_times_sorted_ori, [90, 95, 99, 99.9])
graph_building_times_quantiles = np.percentile(graph_building_times_sorted_ori, [90, 95, 99, 99.9])

# 打印结果
print("\nMatsu Symbolic Execution Times Quantiles (90%, 95%, 99%, 99.9%):")
print(f"90%: {construction_times_quantiles[0]} ms")
print(f"95%: {construction_times_quantiles[1]} ms")
print(f"99%: {construction_times_quantiles[2]} ms")
print(f"99.9%: {construction_times_quantiles[3]} ms")

print("\nGroot Symbolic Execution Times Quantiles (90%, 95%, 99%, 99.9%):")
print(f"90%: {graph_building_times_quantiles[0]} ms")
print(f"95%: {graph_building_times_quantiles[1]} ms")
print(f"99%: {graph_building_times_quantiles[2]} ms")
print(f"99.9%: {graph_building_times_quantiles[3]} ms")


# 取对
construction_times_log = np.log10(np.array(construction_times))
graph_building_times_log = np.log10(np.array(graph_building_times))

construction_times_sorted = np.sort(construction_times_log)
graph_building_times_sorted = np.sort(graph_building_times_log)


# 绘制 CDF 图
plt.figure(figsize=(10, 8))


#100%画图
sns.kdeplot(construction_times_sorted, cumulative=True, label='Symbolic Execution Time (AT)',color='#FF4E48', linewidth=10)
sns.kdeplot(graph_building_times_sorted, cumulative=True, label='Symbolic Execution Time (LG)', color='#0000FF',linewidth=9)

# 标记最大值
max_construction_time = construction_times_sorted[-1]
min_construction_time = construction_times_sorted[0]
max_graph_building_time = graph_building_times_sorted[-1]
mark_AT = construction_times_sorted_ori[-1] / 60000
mark_LG = graph_building_times_sorted_ori[-1] /60000


plt.annotate(
    f'Max: {mark_AT:.2f}min (AT)',
    xy=(max_construction_time, 1.0),
    xytext=(max_construction_time - 2.3 , 0.85),
    arrowprops=dict(facecolor='black', arrowstyle="->", linewidth = 2),
    fontsize=26, 
    fontweight='bold',
    ha='center'
)
plt.annotate(
    f'Max: {mark_LG:.2f}min (LG)',
    xy=(max_graph_building_time, 1.0),
    xytext=(max_graph_building_time - 0.5, 0.7),
    arrowprops=dict(facecolor='black', arrowstyle="->", linewidth=2),
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
plt.xlim(left=min_construction_time)
plt.xlim(right=max_construction_time)
plt.xlabel('CDF of Symbolic Execution Time (ms)', fontsize=30, fontweight='bold')

# 创建字体属性对象
font = FontProperties(weight='bold', size=26)
# 显示图例，并设置字体属性
plt.legend(prop=font, bbox_to_anchor=None, loc='lower right')
formatter = FuncFormatter(lambda x, _: f'$10^{{{x:.0f}}}$' if x > 0 else f'$10^{{{x:.0f}}}$')
ax.xaxis.set_major_formatter(formatter)
plt.tick_params(axis='both', labelsize=18)

# 打开网格，设置线性刻度，确保显示所有数据
plt.grid(True, linestyle='--', linewidth=1.5)


# 保存图像
plt.tight_layout()
plt.savefig('/home/matsu/final_draw/zone_symbolic_time/absolute value/cdf_log_100.png')
plt.show()

# # 计算比率
# merged_df['se time Ratio'] =  merged_df['Property Checking (s)'] / merged_df['symbolic execution and properties checking time (ms)']

# # 获取比率最大的行
# max_ratio_row = merged_df.loc[merged_df['se time Ratio'].idxmax()]

# # 获取比率最小的行
# min_ratio_row = merged_df.loc[merged_df['se time Ratio'].idxmin()]

# # 打印比率最大的信息
# print("\n### Maximum Ratio ###")
# print(f"zone: {max_ratio_row['zone']}")
# print(f"setime of Groot: {max_ratio_row['Property Checking (s)']} ")
# print(f"setime of Matsu: {max_ratio_row['symbolic execution and properties checking time (ms)']} ")
# print(f"se time Ratio: {max_ratio_row['se time Ratio']}")

# # 打印比率最小的信息
# print("\n### Minimum Ratio ###")
# print(f"zone: {min_ratio_row['zone']}")
# print(f"setime of Groot: {min_ratio_row['Property Checking (s)']} ")
# print(f"setime of Matsu: {min_ratio_row['symbolic execution and properties checking time (ms)']} ")
# print(f"se time Ratio: {min_ratio_row['se time Ratio']}")

# # 获取比率数据并排序
# ratios = merged_df['se time Ratio'].dropna()
# ratios_sorted = np.sort(ratios)
# ratios_log = np.log(ratios_sorted)

# # 绘制 CDF 图
# plt.figure(figsize=(10, 8))
# sns.kdeplot(ratios_log, cumulative=True, label='Symbolic Execution Time Ratio',color='#FF7F00',linewidth=5)

# # 标记最大值
# mark = ratios_sorted[-1]
# max_ratio = ratios_log[-1]
# plt.annotate(
#     f'Max: {mark:.2f}',
#     xy=(max_ratio, 1.0),
#     xytext=(max_ratio - 3 , 0.8),
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

# plt.xlim(right=max_ratio)
# plt.xlabel('CDF of LG/AT Symbolic Execution Time Ratio', fontsize=20, fontweight='bold')
# font = FontProperties(weight='bold', size=26)
# plt.legend(prop=font, loc='lower right')
# formatter = FuncFormatter(lambda x, _: f'$10^{{{x:.0f}}}$' if x > 0 else f'$10^{{{x:.0f}}}$')
# ax.xaxis.set_major_formatter(formatter)
# plt.tick_params(axis='both', labelsize=18)
# plt.grid(True, linestyle='--', linewidth=1.5)

# # 保存图像
# plt.tight_layout()
# plt.savefig('/home/matsu/final_draw/zone_symbolic_time/ratio/cdf_log_setime_ratio_new.png')

# plt.show()