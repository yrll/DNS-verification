import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.ticker import FuncFormatter

# 设置文件夹路径
folder_path_AT_time = '/home/matsu/final_v1.1/construction_time_and_memory/matsu_zone_ct_mem.csv'
folder_path_AT_timeG = '/home/matsu/attributes.csv'

# 存储数据
at_data = []
lg_data = []

# 读取 AT Construction 数据
df = pd.read_csv(folder_path_AT_time)
if 'zone' in df.columns and 'construction time (ms)' in df.columns:
    df = df.dropna(subset=['zone', 'construction time (ms)'])
    df = df[df['construction time (ms)'] != 0]
    df['construction time (ms)'] = df['construction time (ms)']
    at_data.append(df[['zone', 'construction time (ms)']])

# 读取 LG Construction 数据
df = pd.read_csv(folder_path_AT_timeG)
if 'Domain' in df.columns and 'Graph building (s)' in df.columns:
    df = df.dropna(subset=['Domain', 'Graph building (s)'])
    df['Graph building (s)'] = df['Graph building (s)'] * 1000
    lg_data.append(df[['Domain', 'Graph building (s)']])

# 合并所有数据
at_df = pd.concat(at_data, ignore_index=True)
lg_df = pd.concat(lg_data, ignore_index=True)

# 根据 "zone" 列对齐数据
merged_df = pd.merge(
    at_df,
    lg_df,
    left_on='zone',
    right_on='Domain',
    how='inner'
)

# 计算比率
merged_df['ct time Ratio'] = merged_df['Graph building (s)'] / merged_df['construction time (ms)']

# 获取比率数据并排序
ratios = merged_df['ct time Ratio'].dropna()

# 获取99%分位数的数据
ratios_99 = ratios[ratios <= np.percentile(ratios, 99)]

# 对99%分位数的数据取对数
ratios_99_log = np.log10(ratios_99)

# 绘制 CDF 图
plt.figure(figsize=(12, 6))
sns.kdeplot(ratios_99_log, cumulative=True, label='Construction Time Ratio (log)', color='#FF7F00', linewidth=8)

# 标记最大值（使用原始数据）
max_ratio = ratios_99.max()
max_ratio_log = np.log10(max_ratio)

plt.annotate(
    f'Max: {max_ratio:.2f}',  # 显示最大值（原数据）
    xy=(max_ratio_log, 1.0),  # 在对数值的位置标记
    xytext=(max_ratio_log - 0.2, 0.8),  # 标注的位置
    arrowprops=dict(facecolor='black', arrowstyle="->", linewidth=2),
    fontsize=26, 
    fontweight='bold',
    ha='center'
)

# 图表美化
ax = plt.gca()
ax.set_ylabel('')
ax.spines['top'].set_linewidth(2)
ax.spines['right'].set_linewidth(2)
ax.spines['bottom'].set_linewidth(2)
ax.spines['left'].set_linewidth(2)

# 设置x轴的最大值
plt.xlim(right=max_ratio_log)

plt.xlabel('CDF of Groot/Matsu Construction Time Ratio (log)', fontsize=24, fontweight='bold')

font = FontProperties(weight='bold', size=26)
plt.legend(prop=font, loc='lower right')
plt.tick_params(axis='both', labelsize=18)
plt.grid(True, linestyle='--', linewidth=1.5)

# 设置 x 轴刻度为 10 的次方格式
formatter = FuncFormatter(lambda x, _: f'$10^{{{x:.0f}}}$' if x > 0 else f'$10^{{{x:.0f}}}$')
ax.xaxis.set_major_formatter(formatter)

# 保存图像
plt.tight_layout()
plt.savefig('/home/matsu/final_draw/zone_construction_time/cdf_bing_ratio99_log.png')

plt.show()
