import pandas as pd
import sys
import glob

def merge_files(input_pattern, output_file):
    input_files = glob.glob(input_pattern)
    if not input_files:
        print("No files found matching the pattern.")
        sys.exit(1)
    dfs = [pd.read_csv(f) for f in input_files]
    merged_df = pd.concat(dfs, ignore_index=True)
    merged_df.to_csv(output_file, index=False)
    print(f"Merged {len(input_files)} files into {output_file}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python merge_files.py <input_pattern> <output_file>")
        sys.exit(1)
    input_pattern = sys.argv[1]
    output_file = sys.argv[2]
    merge_files(input_pattern, output_file)