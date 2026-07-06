import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.ticker import FuncFormatter

# 设置文件夹路径
file_path = '/home/matsu/attributes.csv'

# 存储所有 "Constructing took" 数据
construction_times = []
graph_building_times = []
at_data = []
lg_data = []

# 读取 AT Construction 数据
df = pd.read_csv(file_path)
if 'Domain' in df.columns and 'Total RRs' in df.columns:
    df = df.dropna(subset=['Domain', 'Total RRs'])
    df = df[df['Total RRs'] != 0]
    df['Total RRs'] = df['Total RRs'] 
    at_data.append(df[['Domain', 'Total RRs']])

# 读取 LG Construction 数据
df = pd.read_csv(file_path)
if 'Domain' in df.columns and 'Graph building (s)' in df.columns:
    df = df.dropna(subset=['Domain', 'Graph building (s)'])
    df['Graph building (s)'] = df['Graph building (s)'] * 1000
    lg_data.append(df[['Domain', 'Graph building (s)']])

# 合并所有数据
at_df = pd.concat(at_data, ignore_index=True)
lg_df = pd.concat(lg_data, ignore_index=True)


## 根据 "Domain" 列对齐数据
merged_df = pd.merge(
    at_df,
    lg_df,
    left_on='Domain',
    right_on='Domain',
    how='inner'
)


# 将数据转换为 NumPy 数组并排序
construction_times = merged_df['Total RRs'].dropna()
graph_building_times = merged_df['Graph building (s)'].dropna()
construction_times_log = np.log10(np.array(construction_times))
graph_building_times_log = np.log10(np.array(graph_building_times))

# 打印最大的数据
# 获取最大的行
max_matsu_row = merged_df.loc[merged_df['Total RRs'].idxmax()]


# 打印最大的信息
print("### Max ###")
print(f"zone: {max_matsu_row['Domain']}")
print(f"number of rrs: {max_matsu_row['Total RRs']}")
print(f"cttime: {max_matsu_row['Graph building (s)']} ms")

# 绘制散点图
plt.figure(figsize=(12, 6))

# 绘制散点图，construction_times_log作为横坐标，graph_building_times_log作为纵坐标
plt.scatter(construction_times_log, graph_building_times_log, color='#FF4E48', alpha=0.7)

# 设置标题和轴标签，字体较大且加粗
plt.title('Scatter Plot of Groot RRs vs. Cttime', fontsize=30, fontweight='bold')
plt.xlabel('Number of RRs', fontsize=26, fontweight='bold')
plt.ylabel('Construction Time (ms)', fontsize=26, fontweight='bold')


# 创建字体属性对象
font = FontProperties(weight='bold', size=16)


# 设置坐标轴刻度格式为 10 的次方
formatter = FuncFormatter(lambda x, _: f'$10^{{{x:.0f}}}$' if x > 0 else f'$10^{{{x:.0f}}}$')
plt.gca().xaxis.set_major_formatter(formatter)
plt.gca().yaxis.set_major_formatter(formatter)

# 设置坐标轴刻度大小
plt.tick_params(axis='both', labelsize=22)

# 设置边框线宽
ax = plt.gca()
ax.spines['top'].set_linewidth(2)
ax.spines['right'].set_linewidth(2)
ax.spines['bottom'].set_linewidth(2)
ax.spines['left'].set_linewidth(2)

# 打开网格，设置线性刻度，确保显示所有数据
plt.grid(True, linestyle='--', linewidth=1.5)

# 调整图形布局，避免图例遮挡
plt.tight_layout()

# 保存图像
plt.savefig('/home/matsu/final_draw/groot_rr_vs._cttime/scatter_plot_log.png')

# 显示图像
plt.show()
