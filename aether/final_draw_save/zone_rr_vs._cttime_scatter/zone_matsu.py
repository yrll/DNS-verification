import pandas as pd
import numpy as np
import re
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.ticker import FuncFormatter, MaxNLocator

# 设置文件夹路径
file_path_zonefilesnum= '/home/matsu/final_v1.1/zonfile_num/zonfile_num.csv'
file_path_rrnum = '/home/matsu/attributes.csv'
file_path_cttime = '/home/matsu/final_v1.1/construction_time_and_memory/matsu_zone_ct_mem.csv'

# 存储所有 "Constructing took" 数据
metadomain = []
metafilenum = []
rrnum = []
cttime = []

cnt_data = []
rr_data = []
ct_data = []

# 读取zonefilecount per zone数据存为domain和count
df = pd.read_csv(file_path_zonefilesnum)
if 'Metadata Path' in df.columns and 'ZoneFilesCount' in df.columns:
    df = df.dropna(subset=['Metadata Path', 'ZoneFilesCount'])
    df['Domain'] = df['Metadata Path'].apply(lambda x: re.search(r'/census/([^/]+)/', x).group(1) if re.search(r'/census/([^/]+)/', x) else None)
    df['ZoneFilesCount'] = df['ZoneFilesCount'].astype(int)
    # cnt_data.append(df[['Domain', 'ZoneFilesCount']])
    df_filtered = df[df['ZoneFilesCount'] > 100]
    cnt_data.append(df_filtered[['Domain', 'ZoneFilesCount']])

# 读取 domain和total rrs 数据
df = pd.read_csv(file_path_rrnum)
if 'Domain' in df.columns and 'Total RRs' in df.columns:
    df = df.dropna(subset=['Domain', 'Total RRs'])
    df['Total RRs'] = df['Total RRs'] 
    rr_data.append(df[['Domain', 'Total RRs']])

# 读取cttime数据
df = pd.read_csv(file_path_cttime)
if 'zone' in df.columns and 'construction time (ms)' in df.columns:
    df = df.dropna(subset=['zone', 'construction time (ms)'])
    df['construction time (ms)'] = df['construction time (ms)'] 
    ct_data.append(df[['zone', 'construction time (ms)']])

# 将 cnt_data 和 rr_data 按 Domain 合并
cnt_df = pd.concat(cnt_data, ignore_index=True)
rr_df = pd.concat(rr_data, ignore_index=True)
ct_df = pd.concat(ct_data, ignore_index=True)

merged_cnt_rr_df = pd.merge(cnt_df, rr_df, on='Domain', how='inner')
merged_df = pd.merge(merged_cnt_rr_df, ct_df, left_on='Domain', right_on='zone', how='inner')

# 删除无效的列 'zone'（它与 'Domain' 已经合并）
merged_df = merged_df.drop(columns=['zone'])

# 将数据转换为 NumPy 数组并排序
rrnum = merged_df['Total RRs'].dropna()
cttime = merged_df['construction time (ms)'].dropna()
rrnum_log = np.log10(np.array(rrnum))
cttime_log = np.log10(np.array(cttime))

# # 打印最大的数据
# # 获取最大的行
# max_matsu_row = merged_df.loc[merged_df['Total RRs'].idxmax()]
# # 打印最大的信息
# print("### Max ###")
# print(f"zone: {max_matsu_row['Domain']}")
# print(f"number of rrs: {max_matsu_row['Total RRs']}")
# print(f"cttime: {max_matsu_row['construction time (ms)']} ms")


# 绘制散点图
plt.figure(figsize=(12, 6))

# 绘制散点图，rrnum_log作为横坐标，cttime_log作为纵坐标
plt.scatter(rrnum_log, cttime_log, color='#FF4E48', alpha=0.7)

# 设置标题和轴标签，字体较大且加粗
plt.title('Scatter Plot of Matsu RRs(cnt>100) vs. Cttime', fontsize=30, fontweight='bold')
plt.xlabel('Number of RRs', fontsize=26, fontweight='bold')
plt.ylabel('Construction Time (ms)', fontsize=26, fontweight='bold')


# 创建字体属性对象
font = FontProperties(weight='bold', size=16)


# 设置坐标轴刻度格式为 10 的次方
formatter = FuncFormatter(lambda x, _: f'$10^{{{x:.0f}}}$' if x > 0 else f'$10^{{{x:.0f}}}$')
plt.gca().xaxis.set_major_formatter(formatter)
plt.gca().yaxis.set_major_formatter(formatter)

plt.gca().xaxis.set_major_locator(MaxNLocator(integer=True, prune='both', min_n_ticks=5, steps=[1, 2, 5, 10]))

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
plt.savefig('/home/matsu/final_draw/rr_vs._cttime_scatter/matsu_>100_log.png')

# 显示图像
plt.show()
