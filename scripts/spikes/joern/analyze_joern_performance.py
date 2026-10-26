import pandas as pd

path = "data/interim/joern_spike_results.csv"
df = pd.read_csv(path)

print("\n=== Overall Performance ===")
print(f"Samples: {len(df)}")
print(f"Total processing time: {df['processing_seconds'].sum():.2f} seconds")
print(f"Average per sample: {df['processing_seconds'].mean():.2f} seconds")
print(f"Median per sample: {df['processing_seconds'].median():.2f} seconds")
print(f"Fastest sample: {df['processing_seconds'].min():.2f} seconds")
print(f"Slowest sample: {df['processing_seconds'].max():.2f} seconds")
print(f"Average peak container memory: {df['peak_container_memory_mib'].mean():.2f} MiB")
print(f"Maximum peak container memory: {df['peak_container_memory_mib'].max():.2f} MiB")

print("\n=== Performance by Language ===")
summary = df.groupby("language").agg(
    samples=("sample_index", "count"),
    total_seconds=("processing_seconds", "sum"),
    avg_seconds=("processing_seconds", "mean"),
    median_seconds=("processing_seconds", "median"),
    min_seconds=("processing_seconds", "min"),
    max_seconds=("processing_seconds", "max"),
    avg_peak_memory_mib=("peak_container_memory_mib", "mean"),
    max_peak_memory_mib=("peak_container_memory_mib", "max"),
)

print(summary.round(2).to_string())

print("\n=== Recorded Success Rates ===")
for col in ["parsing_success", "cfg_success", "ddg_success", "pipeline_success"]:
    print(f"{col}: {df[col].sum()}/{len(df)} ({df[col].mean() * 100:.1f}%)")
