import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import os
from matplotlib.font_manager import FontProperties
from matplotlib.ticker import FuncFormatter

# 设置文件夹路径
file_path_Matsu = '/home/matsu/final_v1.1/Matsu_cttime/Matsu_cttime.csv'
file_path_Groot = '/home/matsu/attributes.csv'

mt_data = []
gr_data = []

# 读取mt cttime数据
df = pd.read_csv(file_path_Matsu)
if 'zone' in df.columns and 'construction time (ms)' in df.columns:
    df = df.dropna(subset=['zone', 'construction time (ms)'])
    df['construction time (ms)'] = df['construction time (ms)'] 
    mt_data.append(df[['zone', 'construction time (ms)']])

# 读取cttime数据
df = pd.read_csv(file_path_Groot)
if 'Domain' in df.columns and 'Graph building (s)' in df.columns:
    df = df.dropna(subset=['Domain', 'Graph building (s)'])
    df['Graph building (s)'] = df['Graph building (s)'] * 1000
    gr_data.append(df[['Domain', 'Graph building (s)']])

# 将 cnt_data 和 rr_data 按 Domain 合并
mt_df = pd.concat(mt_data, ignore_index=True)
gr_df = pd.concat(gr_data, ignore_index=True)

merged_df = pd.merge(mt_df, gr_df, left_on='zone', right_on='Domain', how='inner')
# 删除无效的列 'zone'（它与 'Domain' 已经合并）
merged_df = merged_df.drop(columns=['zone'])

# 获取最大的10个construction time和graph building time
top_10_construction_time = merged_df.nlargest(10, 'construction time (ms)')
top_10_graph_building_time =merged_df.nlargest(10, 'Graph building (s)')

# 打印结果
print("Top 10 Construction Times (ms) with corresponding zones:")
print(top_10_construction_time[['Domain', 'construction time (ms)']])

print("\nTop 10 Graph Building Times (s) with corresponding domains:")
print(top_10_graph_building_time[['Domain', 'Graph building (s)']])

# # 将数据转换为 NumPy 数组并排序
# construction_times = merged_df['construction time (ms)'].dropna()
# graph_building_times = merged_df['Graph building (s)'].dropna()
# construction_times_sorted_ori = np.sort(construction_times)
# graph_building_times_sorted_ori =np.sort(graph_building_times) 

# # 计算原始数据的 90%、95%、99%、99.9% 分位数
# construction_times_quantiles = np.percentile(construction_times, [90, 95, 99, 99.9])
# graph_building_times_quantiles = np.percentile(graph_building_times, [90, 95, 99, 99.9])

# # 打印结果
# print("Construction Times Quantiles (90%, 95%, 99%, 99.9%):")
# print(f"90%: {construction_times_quantiles[0]}")
# print(f"95%: {construction_times_quantiles[1]}")
# print(f"99%: {construction_times_quantiles[2]}")
# print(f"99.9%: {construction_times_quantiles[3]}")

# print("\nGraph Building Times Quantiles (90%, 95%, 99%, 99.9%):")
# print(f"90%: {graph_building_times_quantiles[0]}")
# print(f"95%: {graph_building_times_quantiles[1]}")
# print(f"99%: {graph_building_times_quantiles[2]}")
# print(f"99.9%: {graph_building_times_quantiles[3]}")

# # 取对
# construction_times_log = np.log10(np.array(construction_times))
# graph_building_times_log = np.log10(np.array(graph_building_times))

# construction_times_sorted = np.sort(construction_times_log)
# graph_building_times_sorted = np.sort(graph_building_times_log)

# # 绘制 CDF 图
# plt.figure(figsize=(10, 8))


# #100%画图
# sns.kdeplot(construction_times_sorted, cumulative=True, label='Matsu Construction Time',color='#FF4E48',linewidth=10)
# sns.kdeplot(graph_building_times_sorted, cumulative=True, label='Groot Construction Time', color='#0000FF',  linewidth=9)

# # 标记最大值
# max_construction_time = construction_times_sorted[-1]
# max_graph_building_time = graph_building_times_sorted[-1]
# mark_AT = construction_times_sorted_ori[-1] / (1000*60)
# mark_LG = graph_building_times_sorted_ori[-1] / (1000*60)

# plt.annotate(
#     f'Max: {mark_AT:.2f}min (AT)',
#     xy=(max_construction_time, 1.0),
#     xytext=(max_construction_time - 2.3, 0.8), 
#     arrowprops=dict(facecolor='black', arrowstyle="->", linewidth=2),
#     fontsize=30, 
#     fontweight='bold',
#     ha='center'
# )
# plt.annotate(
#     f'Max: {mark_LG:.2f}min (LG)',
#     xy=(max_graph_building_time, 1.0),
#     xytext=(max_graph_building_time - 1.1, 0.55),
#     arrowprops=dict(facecolor='black', arrowstyle="->", linewidth=2),
#     fontsize=30, 
#     fontweight='bold',
#     ha='center'
# )

# # 获取当前轴对象
# ax = plt.gca()
# ax.set_ylabel('')

# # 设置所有四个边框的线条宽度
# ax.spines['top'].set_linewidth(2)    
# ax.spines['right'].set_linewidth(2)   
# ax.spines['bottom'].set_linewidth(2) 
# ax.spines['left'].set_linewidth(2)   

# # 设置标题和轴标签，字体较大且加粗
# # plt.xlim(left=0)
# plt.xlim(right=max_construction_time)
# plt.xlabel('CDF of Construction Time (ms)', fontsize=34, fontweight='bold')
# # 创建字体属性对象
# font = FontProperties(weight='bold', size=26)
# # 显示图例，并设置字体属性
# plt.legend(prop=font, bbox_to_anchor=None, loc='lower right')
# # 设置 x 轴刻度为 10 的次方格式
# formatter = FuncFormatter(lambda x, _: f'$10^{{{x:.0f}}}$' if x > 0 else f'$10^{{{x:.0f}}}$')
# ax.xaxis.set_major_formatter(formatter)

# plt.tick_params(axis='both', labelsize=18)

# # 打开网格，设置线性刻度，确保显示所有数据
# plt.grid(True, linestyle='--', linewidth=1.5)


# # 保存图像
# plt.tight_layout()
# plt.savefig('/home/matsu/final_draw/zone_construction_time/cdf_log_bing_100.pdf')
# plt.show()