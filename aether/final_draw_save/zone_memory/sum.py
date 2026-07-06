import pandas as pd

# 读取 CSV 文件
matsu_df = pd.read_csv('/home/matsu/final_v1.1/construction_time_and_memory/matsu_zone_ct_mem.csv')
groot_df = pd.read_csv('/home/matsu/final_v1.1/construction_time_and_memory/groot_zone_ct_mem.csv')

# 计算 matsu_zone_ct_mem.csv 中 memory lower bound (bytes) 和 memory upper bound (bytes) 列的和，转换为 MB
matsu_memory_lower_bound_sum_mb = matsu_df['memory lower bound (bytes)'].sum() / (1024 * 1024)
matsu_memory_upper_bound_sum_mb = matsu_df['memory upper bound (bytes)'].sum() / (1024 * 1024)

# 计算 groot_zone_ct_mem.csv 中 only domain lec memory (bytes) 和 full lec memory (bytes) 列的和，转换为 MB
groot_only_domain_lec_memory_sum_mb = groot_df['only domain lec memory (bytes)'].sum() / (1024 * 1024)
groot_full_lec_memory_sum_mb = groot_df['full lec memory (bytes)'].sum() / (1024 * 1024)

# 输出结果
print(f"Matsu Zone - Memory Lower Bound Sum: {matsu_memory_lower_bound_sum_mb:.2f} MB")
print(f"Matsu Zone - Memory Upper Bound Sum: {matsu_memory_upper_bound_sum_mb:.2f} MB")
print(f"Groot Zone - Only Domain Lec Memory Sum: {groot_only_domain_lec_memory_sum_mb:.2f} MB")
print(f"Groot Zone - Full Lec Memory Sum: {groot_full_lec_memory_sum_mb:.2f} MB")
