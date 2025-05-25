import os
import pandas as pd
import argparse

# Argument parser for input file
parser = argparse.ArgumentParser(description="Multiply a column by 10 and save new file.")
parser.add_argument("--input_file", type=argparse.FileType('r'), help="Input file")
args = parser.parse_args()

input_path = args.input_file

# Output directory from environment
output_dir = os.getenv("SCRIPTLY_OUTPUT_DIR", "output")
os.makedirs(output_dir, exist_ok=True)

# Read the input CSV
df = pd.read_csv(input_path)

# Automatically pick the first numeric column to multiply
numeric_cols = df.select_dtypes(include=['number']).columns
if not numeric_cols.any():
    raise ValueError("No numeric column found to multiply.")

col_to_multiply = numeric_cols[0]
df[f'{col_to_multiply}_x10'] = df[col_to_multiply] * 10

# Output file path
output_file = os.path.join(output_dir, "multiplied_output.csv")
df.to_csv(output_file, index=False)

print(f"Output written to {output_file}")
