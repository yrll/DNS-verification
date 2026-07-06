import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import os
from matplotlib.font_manager import FontProperties
from matplotlib.ticker import FuncFormatter

# 设置文件夹路径
file_path_Matsu = '/home/matsu/final_v1.1/difference/construction_time_difference.csv'

mt_data = []
gr_data = []

# 读取mt cttime数据
df = pd.read_csv(file_path_Matsu)
if 'zone' in df.columns and 'construction time (ms)' in df.columns and 'Graph building (s)' in df.columns:
    df = df.dropna(subset=['zone', 'Graph building (s)','construction time (ms)'])
    df['construction time (ms)'] = df['construction time (ms)'] 
    mt_data.append(df[['zone', 'Graph building (s)','construction time (ms)']])

# 将 cnt_data 和 rr_data 按 Domain 合并
mt_df = pd.concat(mt_data, ignore_index=True)


# 将数据转换为 NumPy 数组并排序
construction_times = mt_df['construction time (ms)'].dropna()
graph_building_times = mt_df['Graph building (s)'].dropna()

# 过滤掉 0 或负数值，避免对数计算出错
construction_times = construction_times[construction_times > 0]
graph_building_times = graph_building_times[graph_building_times > 0]

construction_times_sorted_ori = np.sort(construction_times)
graph_building_times_sorted_ori =np.sort(graph_building_times) 

# 计算原始数据的 90%、95%、99%、99.9% 分位数
construction_times_quantiles = np.percentile(construction_times, [90, 95, 99, 99.9])
graph_building_times_quantiles = np.percentile(graph_building_times, [90, 95, 99, 99.9])

# 打印结果
print("Construction Times Quantiles (90%, 95%, 99%, 99.9%):")
print(f"90%: {construction_times_quantiles[0] / 60000}")
print(f"95%: {construction_times_quantiles[1]/ 60000}")
print(f"99%: {construction_times_quantiles[2]/ 60000}")
print(f"99.9%: {construction_times_quantiles[3]/ 60000}")

print("\nGraph Building Times Quantiles (90%, 95%, 99%, 99.9%):")
print(f"90%: {graph_building_times_quantiles[0]/ 60000}")
print(f"95%: {graph_building_times_quantiles[1]/ 60000}")
print(f"99%: {graph_building_times_quantiles[2]/ 60000}")
print(f"99.9%: {graph_building_times_quantiles[3]/ 60000}")

# # 取对
# construction_times_log = np.log10(np.array(construction_times))
# graph_building_times_log = np.log10(np.array(graph_building_times))

# construction_times_sorted = np.sort(construction_times_log)
# graph_building_times_sorted = np.sort(graph_building_times_log)

# # 标记最大值
# max_construction_time = construction_times_sorted[-1]
# min_construction_time = construction_times_sorted[0]
# max_graph_building_time = graph_building_times_sorted[-1]
# min_graph_building_time = graph_building_times_sorted[0]

# print("Max Construction Time (log):", max_construction_time)
# print("Min Construction Time (log):", min_construction_time)
# print("Max Graph Building Time (log):", max_graph_building_time)
# print("Min Graph Building Time (log):", min_graph_building_time)


# # 绘制 CDF 图
# plt.figure(figsize=(10, 8))


# #100%画图
# sns.kdeplot(construction_times_sorted, cumulative=True, bw_adjust=0.05, label='Matsu Construction Time',
#             color='#FF4E48', linewidth=10, clip=(min_construction_time, max_construction_time))
# sns.kdeplot(graph_building_times_sorted, cumulative=True, bw_adjust=0.05, label='Groot Construction Time',
#             color='#0000FF', linewidth=9, clip=(min_graph_building_time, max_graph_building_time))



# right=max(max_construction_time,max_graph_building_time)
# left=min(min_construction_time,min_graph_building_time)

# max_construction_time_ori = construction_times_sorted_ori[-1]
# max_graph_building_time_ori = graph_building_times_sorted_ori[-1]
# mark_AT = construction_times_sorted_ori[-1] / (1000*60)
# mark_LG = graph_building_times_sorted_ori[-1] / (1000*60)

# plt.annotate(
#     f'Max: {mark_AT:.2f}min (AT)',
#     xy=(max_construction_time, 1.0),
#     xytext=(max_construction_time - 1, 0.8), 
#     arrowprops=dict(facecolor='black', arrowstyle="->", linewidth=2),
#     fontsize=30, 
#     fontweight='bold',
#     ha='center'
# )
# plt.annotate(
#     f'Max: {mark_LG:.2f}min (LG)',
#     xy=(max_graph_building_time, 1.0),
#     xytext=(max_graph_building_time -0.05, 0.55),
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
# plt.xlim(left=min_graph_building_time)
# plt.xlim(right=max_construction_time)
# plt.xlabel("CDF of Large Zone's Construction Time (ms)", fontsize=24, fontweight='bold')
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
# plt.savefig('/home/matsu/final_draw/difference/cttime/cdf_log_100.png')
# plt.show()