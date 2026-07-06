import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.ticker import FuncFormatter

# 设置文件路径
file_path_Matsu_ct = '/home/matsu/final_v1.1/Matsu_cttime/Matsu_cttime.csv'
file_path_Matsu_se = '/home/matsu/final_v1.1/symbolic_and_checking/matsu_zone_ct_mem_se.csv'
file_path_Groot = '/home/matsu/attributes.csv'

# 存储数据
mt_data = []
gr_data = []
re_data = []

# 读取 Matsu 的建构时间数据
df = pd.read_csv(file_path_Matsu_ct)
if 'zone' in df.columns and 'construction time (ms)' in df.columns:
    df = df.dropna(subset=['zone', 'construction time (ms)'])
    df['construction time (ms)'] = df['construction time (ms)']
    mt_data.append(df[['zone', 'construction time (ms)']])

# 读取 Matsu 的符号执行时间数据
df = pd.read_csv(file_path_Matsu_se)
if 'zone' in df.columns and 'symbolic execution and properties checking time (ms)' in df.columns:
    df = df.dropna(subset=['zone', 'symbolic execution and properties checking time (ms)'])
    df['symbolic execution and properties checking time (ms)'] = df['symbolic execution and properties checking time (ms)']
    gr_data.append(df[['zone', 'symbolic execution and properties checking time (ms)']])

# 读取 Groot 的数据
df = pd.read_csv(file_path_Groot)
if 'Domain' in df.columns and 'Total time (s)' in df.columns:
    df = df.dropna(subset=['Domain', 'Total time (s)'])
    df['Total time (s)'] = df['Total time (s)'] * 1000  # 转换为毫秒
    re_data.append(df[['Domain', 'Total time (s)']])

# 合并所有数据
mt_df = pd.concat(mt_data, ignore_index=True)
gr_df = pd.concat(gr_data, ignore_index=True)
re_df = pd.concat(re_data, ignore_index=True)

merge_df = pd.merge(mt_df, gr_df, on='zone', how='inner')
merged_df = pd.merge(merge_df, re_df, left_on='zone', right_on='Domain', how='inner')

# 计算 Matsu 和 Groot 的端到端时间
matsu_end_to_end_time = merged_df['construction time (ms)'] + merged_df['symbolic execution and properties checking time (ms)']
groot_end_to_end_time = merged_df['Total time (s)']

matsu_end_to_end_time_ori = np.sort(matsu_end_to_end_time)
groot_end_to_end_time_ori = np.sort(groot_end_to_end_time)

# 计算分位数（90%，95%，99%，99.9%）
matsu_quantiles = np.percentile(matsu_end_to_end_time_ori, [90, 95, 99, 99.9])
groot_quantiles = np.percentile(groot_end_to_end_time_ori, [90, 95, 99, 99.9])

# 打印分位数信息
print("\nMatsu End-to-End Time Quantiles (90%, 95%, 99%, 99.9%):")
print(f"90%: {matsu_quantiles[0]} ms")
print(f"95%: {matsu_quantiles[1]} ms")
print(f"99%: {matsu_quantiles[2]} ms")
print(f"99.9%: {matsu_quantiles[3]} ms")

print("\nGroot End-to-End Time Quantiles (90%, 95%, 99%, 99.9%):")
print(f"90%: {groot_quantiles[0]} ms")
print(f"95%: {groot_quantiles[1]} ms")
print(f"99%: {groot_quantiles[2]} ms")
print(f"99.9%: {groot_quantiles[3]} ms")

# 取对数
matsu_log = np.log10(matsu_end_to_end_time)
groot_log = np.log10(groot_end_to_end_time)

# 对数据进行排序
matsu_sorted = np.sort(matsu_log)
groot_sorted = np.sort(groot_log)

# 绘制 CDF 图
plt.figure(figsize=(10, 8))

# 画CDF曲线
sns.kdeplot(matsu_sorted, cumulative=True, label='Matsu End-to-End Time (AT)', color='#FF4E48', linewidth=10)
sns.kdeplot(groot_sorted, cumulative=True, label='Groot End-to-End Time (LG)', color='#0000FF', linewidth=9)

# 标记最大值
max_matsu_time = matsu_sorted[-1]
min_matsu_time = matsu_sorted[0]
max_groot_time = groot_sorted[-1]
mark_AT = matsu_end_to_end_time_ori[-1] / 60000 # 最后的原始时间
mark_LG = groot_end_to_end_time_ori[-1] / 60000 # 最后的原始时间

plt.annotate(
    f'Max: {mark_AT:.2f}min (AT)',
    xy=(max_matsu_time, 1.0),
    xytext=(max_matsu_time - 2.5, 0.85),
    arrowprops=dict(facecolor='black', arrowstyle="->",linewidth=2),
    fontsize=26, 
    fontweight='bold',
    ha='center'
)
plt.annotate(
    f'Max: {mark_LG:.2f}min (LG)',
    xy=(max_groot_time, 1.0),
    xytext=(max_groot_time - 0.5, 0.7),
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
plt.xlim(left=min_matsu_time)
plt.xlim(right=max_matsu_time)
plt.xlabel('CDF of End-to-End Time (ms)', fontsize=30, fontweight='bold')

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
plt.savefig('/home/matsu/final_draw/zone_e2e_time/cdf_log_100.png')
plt.show()
