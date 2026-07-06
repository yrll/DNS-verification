import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import os
from matplotlib.font_manager import FontProperties
from matplotlib.ticker import FuncFormatter

# 设置文件夹路径
file_path_Matsu = '/home/matsu/final_v1.1/construction_time_and_memory/matsu_zone_ct_mem.csv'
file_path_Groot = '/home/matsu/final_v1.1/construction_time_and_memory/groot_zone_ct_mem.csv'

# 存储所有 "Constructing took" 数据
construction_times = []
graph_building_times = []
total_construction_time = 0.0

# 读取 Constructing took 数据

df = pd.read_csv(file_path_Matsu)
if 'memory lower bound (bytes)' in df.columns:
    df = df.dropna(subset=['memory lower bound (bytes)'])
    times = df['memory lower bound (bytes)'] / (1024*1024)
    construction_times.extend(times.tolist())

# 读取 Building label graph took 数据

df = pd.read_csv(file_path_Groot)
if 'full lec memory (bytes)' in df.columns:
    df = df.dropna(subset=['full lec memory (bytes)'])
    times = df['full lec memory (bytes)'] / (1024*1024)
    graph_building_times.extend(times.tolist())

# 将数据转换为 NumPy 数组并排序
construction_times_sorted_ori = np.sort(construction_times)
graph_building_times_sorted_ori = np.sort(graph_building_times)

# # 计算原始数据的 90%、95%、99%、99.9% 分位数
# construction_times_quantiles = np.percentile(construction_times_sorted_ori, [90, 95, 99, 99.9])
# graph_building_times_quantiles = np.percentile(graph_building_times_sorted_ori, [90, 95, 99, 99.9])

# # 打印结果
# print("Construction Times Quantiles (90%, 95%, 99%, 99.9%):")
# print(f"90%: {construction_times_quantiles[0]} MB")
# print(f"95%: {construction_times_quantiles[1]} MB")
# print(f"99%: {construction_times_quantiles[2]} MB")
# print(f"99.9%: {construction_times_quantiles[3]} MB")

# print("\nGraph Building Times Quantiles (90%, 95%, 99%, 99.9%):")
# print(f"90%: {graph_building_times_quantiles[0]} MB")
# print(f"95%: {graph_building_times_quantiles[1]} MB")
# print(f"99%: {graph_building_times_quantiles[2]} MB")
# print(f"99.9%: {graph_building_times_quantiles[3]} MB")

# 取对
construction_times_log = np.log10(np.array(construction_times))
graph_building_times_log = np.log10(np.array(graph_building_times))

construction_times_sorted = np.sort(construction_times_log)
graph_building_times_sorted = np.sort(graph_building_times_log)

# 绘制 CDF 图
plt.figure(figsize=(10, 8))

#100%画图
sns.kdeplot(construction_times_sorted, cumulative=True, label='Matsu Memory Size',color='#FF4E48',linewidth=10)
sns.kdeplot(graph_building_times_sorted, cumulative=True, label='Groot Memory Size', color='#0000FF',  linewidth=8)

# 标记最大值
max_construction_time = construction_times_sorted[-1]
max_graph_building_time = graph_building_times_sorted[-1]
min_construction_time = construction_times_sorted[0]
mark_AT = construction_times_sorted_ori[-1] 
mark_LG = graph_building_times_sorted_ori[-1] 

plt.annotate(
    f'Max: {mark_AT:.2f}MB (AT)',
    xy=(max_construction_time, 1.0),
    xytext=(max_construction_time - 1.5, 0.85), 
    arrowprops=dict(facecolor='black', arrowstyle="->", linewidth=2),
    fontsize=26, 
    fontweight='bold',
    ha='center'
)
plt.annotate(
    f'Max: {mark_LG:.2f}MB (LG)',
    xy=(max_graph_building_time, 1.0),
    xytext=(max_graph_building_time - 1.7, 0.7),
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
plt.xlim(right=max_graph_building_time)
plt.xlabel('CDF of Matsu/Groot Memory Size (MB)', fontsize=30, fontweight='bold')
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
plt.savefig('/home/matsu/final_draw/zone_memory/absolute value/cdf_lower_log_100.png')
plt.show()