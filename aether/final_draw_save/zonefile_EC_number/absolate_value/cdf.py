import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import os
from matplotlib.font_manager import FontProperties
from matplotlib.ticker import FuncFormatter

# 设置文件夹路径
folder_path_AT_time = '/home/matsu/final_v1.1/LEC_num/Matsu_LEC'
folder_path_AT_timeG = '/home/matsu/final_v1.1/LEC_num/Groot_EC'

# 存储数据
at_data = []
lg_data = []
zone_values = []
construction_times = []
graph_building_times = []

# 读取 AT Construction 数据
for filename in os.listdir(folder_path_AT_time):
    if filename.endswith('.csv'):
        file_path = os.path.join(folder_path_AT_time, filename)
        df = pd.read_csv(file_path)
        if 'Constructing ActionTrie for Zone' in df.columns and 'Number of Actions' in df.columns:
            df = df.dropna(subset=['Constructing ActionTrie for Zone', 'Number of Actions'])
            df = df[df['Number of Actions'] != 0]
            df['Number of Actions'] = df['Number of Actions']
            at_data.append(df[['Constructing ActionTrie for Zone', 'Number of Actions']])

# 读取 LG Construction 数据
for filename in os.listdir(folder_path_AT_timeG):
    if filename.endswith('.csv'):
        file_path = os.path.join(folder_path_AT_timeG, filename)
        df = pd.read_csv(file_path)
        if 'Building label graph for zone' in df.columns and 'Number of LECs' in df.columns:
            df = df.dropna(subset=['Building label graph for zone', 'Number of LECs'])
            df['Number of LECs'] = df['Number of LECs'] * 8
            lg_data.append(df[['Building label graph for zone', 'Number of LECs']])

# 合并所有数据
at_df = pd.concat(at_data, ignore_index=True)
lg_df = pd.concat(lg_data, ignore_index=True)


## 根据 "zone" 列对齐数据
merged_df = pd.merge(
    at_df,
    lg_df,
    left_on='Constructing ActionTrie for Zone',
    right_on='Building label graph for zone',
    how='inner'
)

construction_times = merged_df['Number of Actions']
graph_building_times = merged_df['Number of LECs']

# 将数据转换为 NumPy 数组并排序
construction_times_sorted_ori = np.sort(construction_times)
graph_building_times_sorted_ori = np.sort(graph_building_times)

# 计算原始数据的 90%、95%、99%、99.9% 分位数
construction_times_quantiles = np.percentile(construction_times_sorted_ori, [90, 95, 99, 99.9])
graph_building_times_quantiles = np.percentile(graph_building_times_sorted_ori, [90, 95, 99, 99.9])

# 打印结果
print("Construction Times Quantiles (90%, 95%, 99%, 99.9%):")
print(f"90%: {construction_times_quantiles[0]}")
print(f"95%: {construction_times_quantiles[1]}")
print(f"99%: {construction_times_quantiles[2]}")
print(f"99.9%: {construction_times_quantiles[3]}")

print("\nGraph Building Times Quantiles (90%, 95%, 99%, 99.9%):")
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
plt.figure(figsize=(10, 8))

#100%画图
sns.kdeplot(construction_times_sorted, cumulative=True, label='Number of LECs (AT)',color='#FF4E48', linewidth=10)
sns.kdeplot(graph_building_times_sorted, cumulative=True, label='Number of LECs (LG)', color='#0000FF',linewidth=9)

# 标记最大值
max_construction_time = construction_times_sorted[-1]
min_construction_time = construction_times_sorted[0]
max_graph_building_time = graph_building_times_sorted[-1]
mark_AT = int(construction_times_sorted_ori[-1])
mark_LG = int(graph_building_times_sorted_ori[-1]) 


plt.annotate(
    f'Max: {mark_AT} (AT)',
    xy=(max_construction_time, 1.0),
    xytext=(max_construction_time - 1.5, 0.9),
    arrowprops=dict(facecolor='black', arrowstyle="->"),
    fontsize=32, 
    fontweight='bold',
    ha='center'
)
plt.annotate(
    f'Max: {mark_LG} (LG)',
    xy=(max_graph_building_time, 1.0),
    xytext=(max_graph_building_time - 2, 0.8),
    arrowprops=dict(facecolor='black', arrowstyle="->"),
    fontsize=32, 
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
plt.xlabel('CDF of LECs Number', fontsize=34, fontweight='bold')

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
plt.savefig('/home/matsu/final_draw/zonefile_EC_number/absolate_value/cdf_log_100.png')
plt.show()
