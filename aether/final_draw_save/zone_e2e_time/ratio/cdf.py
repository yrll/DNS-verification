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
merged_df['matsu time'] = merged_df['construction time (ms)'] + merged_df['symbolic execution and properties checking time (ms)']
groot_end_to_end_time = merged_df['Total time (s)']

# 过滤掉 0 值
merged_df = merged_df[merged_df['matsu time'] != 0]  


# 计算比率
merged_df['Ratio'] = merged_df['Total time (s)'] / merged_df['matsu time']


# 获取比率数据并排序
ratios = merged_df['Ratio'].dropna()
ratios_sorted_ori = np.sort(np.array(ratios))

# 找到最大和最小的 ratio 值
min_ratio_row = merged_df.loc[merged_df['Ratio'].idxmin()]
max_ratio_row = merged_df.loc[merged_df['Ratio'].idxmax()]

# # 打印最大和最小的 ratio 以及对应的 zone, Graph building 和 construction time
# print(f"Minimum Ratio: {min_ratio_row['Ratio']:.2f}")
# print(f"Zone: {min_ratio_row['zone']}, Graph Building (s): {min_ratio_row['Graph building (s)']}, Construction Time (ms): {min_ratio_row['construction time (ms)']}")
# print(f"Maximum Ratio: {max_ratio_row['Ratio']:.2f}")
# print(f"Zone: {max_ratio_row['zone']}, Graph Building (s): {max_ratio_row['Graph building (s)']}, Construction Time (ms): {max_ratio_row['construction time (ms)']}")


# 计算小于1的数据个数
count_less_than_1 = sum(ratios < 1)
print(f"Number of ratios less than 1: {count_less_than_1}")

# 计算99%分位数
quantile_90 = np.percentile(ratios_sorted_ori, 90)
quantile_99 = np.percentile(ratios_sorted_ori, 99)
quantile_95 = np.percentile(ratios_sorted_ori, 95)
quantile_999 = np.percentile(ratios_sorted_ori, 99.9)
print(f"90th Percentile : {quantile_90}")
print(f"95th Percentile : {quantile_95}")
print(f"99th Percentile : {quantile_99}")
print(f"99.9th Percentile : {quantile_999}")

# 找到 ratio 小于 1 的数据
less_than_1_df = merged_df[merged_df['Ratio'] < 1]

# 计算 difference 列：construction time (ms) - Graph building (s)
less_than_1_df.loc[:, 'difference'] = less_than_1_df['matsu time'] - less_than_1_df['Total time (s)']


# 写入 CSV 文件
less_than_1_df = less_than_1_df[['zone', 'Total time (s)', 'matsu time', 'Ratio', 'difference']]
less_than_1_df.to_csv('/home/matsu/final_draw/zone_e2e_time/difference.csv', index=False)

# 对比率数据取对数（避免0或负数，确保对数运算有效）
ratios_log = np.log10(np.array(ratios_sorted_ori))
ratios_sorted = np.sort(ratios_log)

# 绘制 CDF 图
plt.figure(figsize=(10, 8))
sns.kdeplot(ratios_sorted, cumulative=True, label='End-to-End Time Ratio', color='#FF7F00', linewidth=10)

# 标记最大值
max_ratio = ratios_sorted_ori[-1]  # 使用对数值计算对应的原始值
plt.annotate(
    f'Max: {max_ratio:.2f}',  # 显示最大值
    xy=(ratios_sorted[-1], 1.0),
    xytext=(ratios_sorted[-1] - 1.6, 0.8),
    arrowprops=dict(facecolor='black', arrowstyle="->", linewidth=2),
    fontsize=30, 
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

# 设置x轴的最大值，使用log值
plt.xlim(left=ratios_sorted[0])
plt.xlim(right=ratios_sorted[-1])

plt.xlabel('CDF of End-to-End Time Ratio', fontsize=30, fontweight='bold')

font = FontProperties(weight='bold', size=30)
plt.legend(prop=font, loc='lower right')
plt.tick_params(axis='both', labelsize=18)
plt.grid(True, linestyle='--', linewidth=1.5)

# 设置 x 轴刻度为 10 的次方格式
formatter = FuncFormatter(lambda x, _: f'$10^{{{x:.0f}}}$' if x > 0 else f'$10^{{{x:.0f}}}$')
ax.xaxis.set_major_formatter(formatter)

# 保存图像
plt.tight_layout()
plt.savefig('/home/matsu/final_draw/zone_e2e_time/ratio/cdf_e2e_ratio.png')

plt.show()