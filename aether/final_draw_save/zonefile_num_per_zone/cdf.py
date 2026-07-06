import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import os
from matplotlib.font_manager import FontProperties
from matplotlib.ticker import FuncFormatter

# 设置文件夹路径
file_path = '/home/matsu/final_v1.1/zonfile_num/zonfile_num.csv'

# 存储所有 "Constructing took" 数据
construction_times = []

# 读取 Constructing took 数据

df = pd.read_csv(file_path)
if 'ZoneFilesCount' in df.columns:
    df = df.dropna(subset=['ZoneFilesCount'])
    times = df['ZoneFilesCount']
    construction_times.extend(times.tolist())

# # 获取最大的十个原始数据以及它们对应的 Metadata Path
# top_10_df = df.nlargest(20, 'ZoneFilesCount')[['ZoneFilesCount', 'Metadata Path']]

# # 打印最大的十个原数据及其对应的 Metadata Path
# print("Top 20 Largest ZoneFilesCount and Corresponding Metadata Path:")
# print(top_10_df)

# 将数据转换为 NumPy 数组并排序
construction_times_sorted_ori = np.sort(construction_times)


# # 计算原始数据的 90%、95%、99%、99.9% 分位数
# construction_times_quantiles = np.percentile(construction_times_sorted_ori, [90, 95, 99, 99.9])

# # 打印结果
# print("Construction Times Quantiles (90%, 95%, 99%, 99.9%):")
# print(f"90%: {construction_times_quantiles[0]}")
# print(f"95%: {construction_times_quantiles[1]}")
# print(f"99%: {construction_times_quantiles[2]}")
# print(f"99.9%: {construction_times_quantiles[3]}")

# 取对
construction_times_log = np.log10(np.array(construction_times))
construction_times_sorted = np.sort(construction_times_log)


# 绘制 CDF 图
plt.figure(figsize=(10, 8))

#100%画图
sns.kdeplot(construction_times_sorted, cumulative=True, label='Zonefile Number',color='#FF7F00',linewidth=10)

# 标记最大值
max_construction_time = construction_times_sorted[-1]
min_construction_time = construction_times_sorted[0]
mark_AT = construction_times_sorted_ori[-1] 


plt.annotate(
    f'Max: {mark_AT:.0f}',
    xy=(max_construction_time, 1.0),
    xytext=(max_construction_time - 0.8, 0.85), 
    arrowprops=dict(facecolor='black', arrowstyle="->",linewidth=2),
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
plt.xlabel('CDF of Zonefile Number Per Zone', fontsize=30, fontweight='bold')
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
plt.savefig('/home/matsu/final_draw/zonefile_num_per_zone/cdf_log_100.png')
plt.show()