import os 
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

# 设置文件夹路径
folder_path_Groot = '/home/matsu/attributes.csv'
folder_path_Groot_simu1 = '/home/matsu/final_v1.1/construction_time_and_memory/groot_zone_ct_mem.csv'
file_path_Matsu = '/home/matsu/final_v1.1/construction_time_and_memory/matsu_zonefile_ct_mem.csv'

# 存储数据
at_data = []
lg_data = []
si_data = []

# 读取 AT Construction 数据
df = pd.read_csv(file_path_Matsu)
if 'zone' in df.columns and 'construction time (ms)' in df.columns:
    df = df.dropna(subset=['zone', 'construction time (ms)'])
    df = df[df['construction time (ms)'] != 0]
    df['construction time (ms)'] = df['construction time (ms)'].astype(float)
    at_data.append(df[['zone', 'construction time (ms)']])

# 读取 AT Construction 数据
df = pd.read_csv(folder_path_Groot)
if 'Domain' in df.columns and 'Graph building (s)' in df.columns:
    df = df.dropna(subset=['Domain', 'Graph building (s)'])
    df = df[df['Graph building (s)'] != 0]
    df['Graph building (s)'] = df['Graph building (s)'] * 1000  # 转换为毫秒
    lg_data.append(df[['Domain', 'Graph building (s)']])

# 读取 Simu-LG Construction 数据
df = pd.read_csv(folder_path_Groot_simu1)
if 'zone' in df.columns and 'total time (ms)' in df.columns:
    df = df.dropna(subset=['zone', 'total time (ms)'])
    df['total time (ms)'] = df['total time (ms)']  # 保持毫秒单位
    si_data.append(df[['zone', 'total time (ms)']])

# 合并所有数据
at_df = pd.concat(at_data, ignore_index=True)
lg_df = pd.concat(lg_data, ignore_index=True)
si_df = pd.concat(si_data, ignore_index=True)

# 根据 "zone" 列对齐数据

# 根据 "zone" 列对齐数据
merged_df = pd.merge(
    lg_df,
    si_df,
    left_on='Domain',
    right_on='zone',
    how='inner'
)


# 计算总时间（以分钟为单位）
matsu_total = at_df['construction time (ms)'].max() / 60000
groot_total = merged_df['Graph building (s)'].sum() / 60000  # 转换为分钟
groot_simu = merged_df['total time (ms)'].sum() / 60000  # 转换为分钟

# 打印计算出的总时间（以分钟为单位）
print(f"Total Matsu Construction Time: {matsu_total:.2f} minutes")
print(f"Total Groot Graph Building Time: {groot_total:.2f} minutes")
print(f"Total Groot Simulation Time: {groot_simu:.2f} minutes")

# 画柱状图
labels = ['Matsu Construction Time', 'Groot Graph Building Time', 'Groot Simulation Time']
values = [matsu_total, groot_total, groot_simu]  # 转换 Matsu 时间为秒，其他时间已经是分钟

fig, ax = plt.subplots(figsize=(12, 8))

# 设置柱子的宽度和间距
bar_width = 0.15  # 缩小柱子的宽度
bar_spacing = 2.0  # 缩小柱子之间的间距

# 画柱状图
bars = ax.bar(labels, values, width=bar_width, color=['#FF4E48', '#0000FF', '#00FF00'], align='center')

# 标记最大值在柱子顶端
for bar, value in zip(bars, values):
    ax.text(
        bar.get_x() + bar.get_width() / 2,  # x位置：柱子的中心
        bar.get_height() + 0.03,  # y位置：柱子的顶端
        f'{value:.2f} min',  # 显示的文本
        ha='center',  # 水平对齐
        va='bottom',  # 垂直对齐
        fontsize=18, 
        fontweight='bold',
        color='black'
    )

# 设置标题和坐标轴标签
ax.set_xlabel('Construction Time Comparison (minutes)', fontsize=24, fontweight='bold')
ax.set_ylabel('Time (minutes)', fontsize=24, fontweight='bold')

# 设置坐标轴线宽
ax.spines['top'].set_linewidth(2)    
ax.spines['right'].set_linewidth(2)   
ax.spines['bottom'].set_linewidth(2) 
ax.spines['left'].set_linewidth(2)   

# 创建字体属性对象
font = FontProperties(weight='bold', size=18)

# 设置x轴刻度标签大小
plt.xticks(fontsize=14, fontweight='bold')

# 设置y轴刻度标签大小
plt.yticks(fontsize=14, fontweight='bold')

# 设置图例
ax.legend(
    bars,  # 将柱状图对象传入图例
    ['Matsu Construction Time', 'Groot Construction Time', 'Groot Simulation Time'],  # 图例对应的标签
    loc='upper left',  # 图例位置
    prop=font, 
    fontsize=16,  # 设置图例字体大小
)

# 增大 y 轴的上限
y_max = max(values) * 1.3  # 设置为数据最大值的1.3倍，以保证有足够的空间
ax.set_ylim(0, y_max)  # 设置y轴范围

# 打开网格，设置线性刻度，确保显示所有数据
plt.grid(True, linestyle='--', linewidth=1.5)

# 保存图像
output_file = '/home/matsu/final_draw/cttime_bar/construction_time_comparison_minutes_simu.png'
plt.tight_layout()
plt.savefig(output_file)

# 显示图表
plt.show()
