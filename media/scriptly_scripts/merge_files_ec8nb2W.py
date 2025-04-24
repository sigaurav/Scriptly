import pandas as pd
import argparse

def merge_files(input_files, output_file):
    if not input_files:
        print("No files provided.")
        return
    dfs = [pd.read_csv(f) for f in input_files]
    merged_df = pd.concat(dfs, ignore_index=True)
    merged_df.to_csv(output_file, index=False)
    print(f"Merged {len(input_files)} files into {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge multiple CSV files into a single file.")
    parser.add_argument("input_files", nargs="+", help="Paths to the input CSV files (at least one required)")
    parser.add_argument("output_file", help="Path to the output CSV file")
    args = parser.parse_args()

    merge_files(args.input_files, args.output_file)