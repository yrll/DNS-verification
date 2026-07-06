import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
from matplotlib.font_manager import FontProperties
from matplotlib.ticker import FuncFormatter
from statsmodels.distributions.empirical_distribution import ECDF

# 设置文件夹路径
file_path_Matsu = '/home/matsu/final_v1.1/difference/construction_time_difference.csv'

mt_data = []
gr_data = []

# 读取mt cttime数据
df = pd.read_csv(file_path_Matsu)
if 'zone' in df.columns and 'construction time (ms)' in df.columns and 'Graph building (s)' in df.columns:
    df = df.dropna(subset=['zone', 'Graph building (s)', 'construction time (ms)'])
    df['construction time (ms)'] = df['construction time (ms)']
    mt_data.append(df[['zone', 'Graph building (s)', 'construction time (ms)']])

# 将数据合并
mt_df = pd.concat(mt_data, ignore_index=True)

# 将数据转换为 NumPy 数组并排序
construction_times = mt_df['construction time (ms)'].dropna()
graph_building_times = mt_df['Graph building (s)'].dropna()

# 过滤掉 0 或负数值，避免对数计算出错
construction_times = construction_times[construction_times > 0]
graph_building_times = graph_building_times[graph_building_times > 0]

# 对数变换数据
construction_times_log = np.log10(np.array(construction_times))
graph_building_times_log = np.log10(np.array(graph_building_times))

# 计算 ECDF
ecdf_construction = ECDF(construction_times_log)
ecdf_graph_building = ECDF(graph_building_times_log)

# 标记最大值
max_construction_time = construction_times_log.max()
max_graph_building_time = graph_building_times_log.max()
mark_AT = construction_times.max() / (1000 * 60)
mark_LG = graph_building_times.max() / (1000 * 60)

# 绘制 ECDF 图
plt.figure(figsize=(10, 8))

# 绘制 ECDF 曲线
plt.plot(ecdf_construction.x, ecdf_construction.y, label='Matsu Construction Time', color='#FF4E48', linewidth=3)
plt.plot(ecdf_graph_building.x, ecdf_graph_building.y, label='Groot Construction Time', color='#0000FF', linewidth=3)

# 添加标注
plt.annotate(
    f'Max: {mark_AT:.2f}min (AT)',
    xy=(max_construction_time, 1.0),
    xytext=(max_construction_time, 0.8),
    arrowprops=dict(facecolor='black', arrowstyle="->", linewidth=2),
    fontsize=15, fontweight='bold', ha='center'
)
plt.annotate(
    f'Max: {mark_LG:.2f}min (LG)',
    xy=(max_graph_building_time, 1.0),
    xytext=(max_graph_building_time, 0.6),
    arrowprops=dict(facecolor='black', arrowstyle="->", linewidth=2),
    fontsize=15, fontweight='bold', ha='center'
)

# 设置图例和坐标轴
plt.xlabel("CDF of Large Zone's Construction Time (log10(ms))", fontsize=16, fontweight='bold')
plt.ylabel("CDF", fontsize=16, fontweight='bold')
plt.legend(fontsize=14, loc='lower right')

# 设置 x 轴为对数刻度格式
formatter = FuncFormatter(lambda x, _: f'$10^{{{x:.0f}}}$')
plt.gca().xaxis.set_major_formatter(formatter)
plt.tick_params(axis='both', labelsize=12)
plt.grid(True, linestyle='--', linewidth=0.7)

# 保存并显示图像
plt.tight_layout()
plt.savefig('/home/matsu/final_draw/difference/cttime/ecdf_log.png')
plt.show()
