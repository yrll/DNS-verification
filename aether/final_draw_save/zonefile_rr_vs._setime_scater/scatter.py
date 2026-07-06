import pandas as pd
import numpy as np
import re
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.ticker import FuncFormatter, MaxNLocator

# 设置文件夹路径

file_path_rrnum = '/home/matsu/attributes.csv'
file_path_matsu_cttime = '/home/matsu/final_v1.1/symbolic_and_checking/matsu_zone_ct_mem_se.csv'
file_path_groot_cttime = '/home/matsu/attributes.csv'

# 存储所有 "Constructing took" 数据
metadomain = []
metafilenum = []
rrnum = []
mttime = []
grtime = []


rr_data = []
mt_data = []
gr_data = []


# 读取 domain和total rrs 数据
df = pd.read_csv(file_path_rrnum)
if 'Domain' in df.columns and 'Total RRs' in df.columns:
    df = df.dropna(subset=['Domain', 'Total RRs'])
    df['Total RRs'] = df['Total RRs'] 
    rr_data.append(df[['Domain', 'Total RRs']])

# 读取mt cttime数据
df = pd.read_csv(file_path_matsu_cttime)
if 'zone' in df.columns and 'symbolic execution and properties checking time (ms)' in df.columns:
    df = df.dropna(subset=['zone', 'symbolic execution and properties checking time (ms)'])
    df = df[df['symbolic execution and properties checking time (ms)'] > 0] 
    mt_data.append(df[['zone', 'symbolic execution and properties checking time (ms)']])

# 读取cttime数据
df = pd.read_csv(file_path_groot_cttime)
if 'Domain' in df.columns and 'Property Checking (s)' in df.columns:
    df = df.dropna(subset=['Domain', 'Property Checking (s)'])
    df['Property Checking (s)'] = df['Property Checking (s)'] * 1000
    gr_data.append(df[['Domain', 'Property Checking (s)']])

# 将 cnt_data 和 rr_data 按 Domain 合并

rr_df = pd.concat(rr_data, ignore_index=True)
mt_df = pd.concat(mt_data, ignore_index=True)
gr_df = pd.concat(gr_data, ignore_index=True)

merged_mt_df = pd.merge(rr_df, mt_df, left_on='Domain', right_on='zone', how='inner')
merged_df = pd.merge(merged_mt_df, gr_df, left_on='Domain', right_on='Domain', how='inner')
# 删除无效的列 'zone'（它与 'Domain' 已经合并）
merged_df = merged_df.drop(columns=['zone'])

# 打印符合条件的数据
filtered_df = merged_df[(merged_df['Total RRs'].between(10**2, 10**3)) & 
                        (merged_df['symbolic execution and properties checking time (ms)'] > 10**4)]

print("### Filtered Zones ###")
for _, row in filtered_df.iterrows():
    print(f"zone: {row['Domain']}, rrnum: {row['Total RRs']}, time: {row['symbolic execution and properties checking time (ms)']} ms")



# 将数据转换为 NumPy 数组并排序
rrnum = merged_df['Total RRs'].dropna()
mttime = merged_df['symbolic execution and properties checking time (ms)'].dropna()
grtime = merged_df['Property Checking (s)'].dropna()
rrnum_log = np.log10(np.array(rrnum))
mttime_log = np.log10(np.array(mttime))
grtime_log = np.log10(np.array(grtime))

# 打印最大的数据
# 获取最大的行
max_matsu_row = merged_df.loc[merged_df['Total RRs'].idxmax()]

# 打印最大的信息
print("### Max ###")
print(f"zone: {max_matsu_row['Domain']}")
print(f"number of rrs: {max_matsu_row['Total RRs']}")
print(f"matsu time: {max_matsu_row['symbolic execution and properties checking time (ms)']} ms")
print(f"groot time: {max_matsu_row['Property Checking (s)']} ms")


# 绘制散点图
plt.figure(figsize=(10, 8))

# 绘制散点图，rrnum_log作为横坐标，cttime_log作为纵坐标
plt.scatter(rrnum_log, mttime_log, color='#FF4E48', label='Matsu',alpha=0.7)
plt.scatter(rrnum_log, grtime_log, color='#0000FF', label='Groot',alpha=0.7)
plt.legend(fontsize=22,loc='lower right')

# 设置标题和轴标签，字体较大且加粗
plt.title(' Scatter of RRs Per Zone vs. Symbolic Execition Time', fontsize=20, fontweight='bold')
plt.xlabel('Number of RRs Per Zonefile', fontsize=28, fontweight='bold')
plt.ylabel('Symbolic Execution Time (ms)', fontsize=28, fontweight='bold')


# 创建字体属性对象
font = FontProperties(weight='bold', size=16)


# 设置坐标轴刻度格式为 10 的次方
formatter = FuncFormatter(lambda x, _: f'$10^{{{x:.0f}}}$' if x > 0 else f'$10^{{{x:.0f}}}$')
plt.gca().xaxis.set_major_formatter(formatter)
plt.gca().yaxis.set_major_formatter(formatter)

# plt.gca().xaxis.set_major_locator(MaxNLocator(integer=True, prune='both', min_n_ticks=7, steps=[1, 2, 5, 10]))

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
plt.savefig('/home/matsu/final_draw/zonefile_rr_vs._setime_scater/matsuandgroot_log.png')

# 显示图像
plt.show()
