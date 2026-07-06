import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import os
from matplotlib.font_manager import FontProperties

# 设置文件夹路径
folder_path_AT_time = '/home/matsu/final_v1.1/LEC_num/Matsu_LEC'
folder_path_AT_timeG = '/home/matsu/final_v1.1/LEC_num/Groot_EC'

# 存储数据
at_data = []
lg_data = []

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

# 根据 "zone" 列对齐数据
merged_df = pd.merge(
    at_df,
    lg_df,
    left_on='Constructing ActionTrie for Zone',
    right_on='Building label graph for zone',
    how='inner'
)

# 计算比率
merged_df['ECs Ratio'] =  merged_df['Number of LECs'] / merged_df['Number of Actions']

# 获取比率数据并排序
ratios = merged_df['ECs Ratio'].dropna()
ratios_sorted = np.sort(ratios)

# 计算99%分位数
quantile_99 = np.percentile(ratios_sorted, 99)
quantile_95 = np.percentile(ratios_sorted, 95)

# 绘制 CDF 图
plt.figure(figsize=(12, 6))
sns.kdeplot(ratios_sorted, cumulative=True, label='ECs Number Ratio', color='#FF7F00', linewidth=8)

# # 使用箭头标注分位数
# plt.annotate(
#     f'95% Quantile: {quantile_95:.2f}',
#     xy=(quantile_95, 0.99),  # 箭头指向位置
#     xytext=(quantile_95 + 85, 0.6),  # 注释文本位置
#     arrowprops=dict(facecolor='blue', arrowstyle="->", linewidth=2),
#     fontsize=26,
#     fontweight='bold',
#     ha='center'
# )
# plt.annotate(
#     f'99% Quantile: {quantile_99:.2f}',
#     xy=(quantile_99, 0.99),  # 箭头指向位置
#     xytext=(quantile_99 + 60, 0.8),  # 注释文本位置
#     arrowprops=dict(facecolor='blue', arrowstyle="->", linewidth=2),
#     fontsize=26,
#     fontweight='bold',
#     ha='center'
# )

# 绘制从分位点向右和向下引虚线（灰色）
plt.vlines(quantile_95, 0, 0.95, colors='gray', linestyles='dashed', linewidth=2)  # 只向下延伸
plt.hlines(0.95, 0, quantile_95, colors='gray', linestyles='dashed', linewidth=2)  # 只向右延伸
plt.text(quantile_95 + 10, 0.85, f'95% Quantile: {quantile_95:.2f}', color='black', fontsize=26, fontweight='bold')

plt.vlines(quantile_99, 0, 0.99, colors='gray', linestyles='dashed', linewidth=2)  # 只向下延伸
plt.hlines(0.99, 0, quantile_99, colors='gray', linestyles='dashed', linewidth=2)  # 只向右延伸
plt.text(quantile_99 + 10, 0.75, f'99% Quantile: {quantile_99:.2f}', color='black', fontsize=26, fontweight='bold')

# 标记最大值
max_ratio = ratios_sorted[-1]
plt.annotate(
    f'Max: {max_ratio}',
    xy=(max_ratio, 1.0),
    xytext=(max_ratio-50, 0.8),
    arrowprops=dict(facecolor='black', arrowstyle="->", linewidth=2),
    fontsize=26, 
    fontweight='bold',
    ha='center'
)

# 图表美化
ax = plt.gca()
ax.spines['top'].set_linewidth(2)
ax.spines['right'].set_linewidth(2)
ax.spines['bottom'].set_linewidth(2)
ax.spines['left'].set_linewidth(2)

plt.xlim(left=0, right=max(ratios_sorted))
plt.xlabel('CDF of Groot/Matsu ECs Number Ratio', fontsize=30, fontweight='bold')
plt.ylabel('CDF', fontsize=24, fontweight='bold')
font = FontProperties(weight='bold', size=26)
plt.legend(prop=font, loc='lower right')
plt.tick_params(axis='both', labelsize=18)
plt.grid(True, linestyle='--', linewidth=1.5)

# 保存图像
plt.tight_layout()
plt.savefig('/home/matsu/final_draw/EC_number/ratio/cdf_ratio_with_new_quantile.png')
plt.show()
