import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import os
from matplotlib.font_manager import FontProperties
from matplotlib.ticker import FuncFormatter

# 设置文件夹路径
file_path = '/home/matsu/final_draw/zone_e2e_time/difference.csv'

# 读取数据
df = pd.read_csv(file_path)

# 检查数据中是否有 'difference' 列，并删除缺失值
if 'difference' in df.columns:
    df = df.dropna(subset=['difference'])

# 提取 'difference' 列数据
difference_data = df['difference']

# 将数据转换为 NumPy 数组并排序
difference_sorted = np.sort(difference_data)

# 计算原始数据的 90%、95%、99%、99.9% 分位数
difference_quantiles = np.percentile(difference_sorted, [90, 95, 99, 99.9])

# 打印分位数结果
print("\nDifference Column Quantiles (90%, 95%, 99%, 99.9%):")
print(f"90%: {difference_quantiles[0]} ms")
print(f"95%: {difference_quantiles[1]} ms")
print(f"99%: {difference_quantiles[2]} ms")
print(f"99.9%: {difference_quantiles[3]} ms")

# 取对数（log10）
difference_log = np.log10(difference_sorted)

# 绘制 CDF 图
plt.figure(figsize=(10, 8))

# 绘制 difference 的 CDF 图
sns.kdeplot(difference_log, cumulative=True, label='Difference ', color='#FF7F00', linewidth=10)

# 获取最大值和最小值
max_difference = difference_log[-1]
min_difference = difference_log[0]
mark = difference_sorted[-1] / 60000

# 标记最大值
plt.annotate(
    f'Max: {mark:.2f}min',
    xy=(max_difference, 1.0),
    xytext=(max_difference - 1.5, 0.85),
    arrowprops=dict(facecolor='black', arrowstyle="->", linewidth=2),
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
plt.xlim(left=min_difference)
plt.xlim(right=max_difference)
plt.xlabel('CDF of End-to-End Difference Time(ms)', fontsize=24, fontweight='bold')

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
plt.savefig('/home/matsu/final_draw/zone_e2e_time/difference/cdf_log_difference.png')
plt.show()
