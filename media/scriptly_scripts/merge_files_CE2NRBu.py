import pandas as pd
import sys

def merge_files(input_files, output_file):
    if not input_files:
        print("No files provided.")
        sys.exit(1)
    dfs = [pd.read_csv(f) for f in input_files]
    merged_df = pd.concat(dfs, ignore_index=True)
    merged_df.to_csv(output_file, index=False)
    print(f"Merged {len(input_files)} files into {output_file}")

if __name__ == "__main__":
    # Check if the script is being run by Scriptly's parser
    if "scriptly" in sys.argv[0].lower() or len(sys.argv) < 3:
        # Skip execution during parsing
        pass
    else:
        if len(sys.argv) < 3:
            print("Usage: python merge_files.py <input_file1> <input_file2> ... <output_file>")
            sys.exit(1)
        input_files = sys.argv[1:-1]
        output_file = sys.argv[-1]
        merge_files(input_files, output_file)