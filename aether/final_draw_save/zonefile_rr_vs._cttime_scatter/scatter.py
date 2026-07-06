import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

# 设置文件夹路径
file_path_rrnum = '/home/matsu/groot_bing/attributes_single_file.csv'
file_path_matsu_cttime = '/home/matsu/final_v1.1/construction_time_and_memory/matsu_zonefile_ct_mem.csv'


# 存储所有 "Constructing took" 数据
rr_data = []
mt_data = []


# 读取 domain和total rrs 数据
df = pd.read_csv(file_path_rrnum)
if 'Domain' in df.columns and 'Total RRs' in df.columns and 'Graph building (s)' in df.columns:
    df = df.dropna(subset=['Domain', 'Total RRs', 'Graph building (s)'])
    df['Graph building (s)'] = df['Graph building (s)'] * 1000
    rr_data.append(df[['Domain', 'Total RRs', 'Graph building (s)']])

# 读取mt cttime数据
df = pd.read_csv(file_path_matsu_cttime)
if 'zone' in df.columns and 'construction time (ms)' in df.columns:
    df = df.dropna(subset=['zone', 'construction time (ms)'])
    mt_data.append(df[['zone', 'construction time (ms)']])



# 将 cnt_data 和 rr_data 按 Domain 合并
rr_df = pd.concat(rr_data, ignore_index=True)
mt_df = pd.concat(mt_data, ignore_index=True)


merged_df = pd.merge(rr_df, mt_df, left_on='Domain', right_on='zone', how='inner')

# 删除无效的列 'zone'（它与 'Domain' 已经合并）
merged_df = merged_df.drop(columns=['zone'])

# 打印合并后数据的长度
print(f"Length of merged data: {len(merged_df)}")

# 获取最大 mttime 和对应的 rrnum 和 domain
max_mttime_row = merged_df.loc[merged_df['construction time (ms)'].idxmax()]
print("### Max Matsu Time ###")
print(f"Domain: {max_mttime_row['Domain']}")
print(f"Number of RRs: {max_mttime_row['Total RRs']}")
print(f"Matsu Time: {max_mttime_row['construction time (ms)']} ms")
print(f"Groot Time: {max_mttime_row['Graph building (s)']} ms")

# 获取最大 grtime 和对应的 rrnum 和 domain
max_grtime_row = merged_df.loc[merged_df['Graph building (s)'].idxmax()]
print("### Max Groot Time ###")
print(f"Domain: {max_grtime_row['Domain']}")
print(f"Number of RRs: {max_grtime_row['Total RRs']}")
print(f"Matsu Time: {max_grtime_row['construction time (ms)']} ms")
print(f"Groot Time: {max_grtime_row['Graph building (s)']} ms")

# 获取最大 rrnum 和对应的 mttime 和 grtime
max_rrnum_row = merged_df.loc[merged_df['Total RRs'].idxmax()]
print("### Max Number of RRs ###")
print(f"Domain: {max_rrnum_row['Domain']}")
print(f"Number of RRs: {max_rrnum_row['Total RRs']}")
print(f"Matsu Time: {max_rrnum_row['construction time (ms)']} ms")
print(f"Groot Time: {max_rrnum_row['Graph building (s)']} ms")

# 绘制散点图
rrnum = merged_df['Total RRs']
mttime = merged_df['construction time (ms)']
grtime = merged_df['Graph building (s)']

plt.figure(figsize=(12, 6))

# 绘制散点图，rrnum作为横坐标，mttime和grtime作为纵坐标
plt.scatter(rrnum, mttime, color='#FF4E48', label='Matsu', alpha=0.7)
plt.scatter(rrnum, grtime, color='#0000FF', label='Groot', alpha=0.7)
plt.legend(fontsize=22, loc='upper right')

# 设置标题和轴标签，字体较大且加粗
plt.title('Matsu Groot RRs vs. Cttime', fontsize=26, fontweight='bold')
plt.xlabel('Number of RRs', fontsize=26, fontweight='bold')
plt.ylabel('Construction Time (ms)', fontsize=26, fontweight='bold')

# 创建字体属性对象
font = FontProperties(weight='bold', size=16)

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
plt.savefig('/home/matsu/final_draw/zonefile_rr_vs._cttime_scatter/matsuandgroot.png')

# 显示图像
plt.show()
