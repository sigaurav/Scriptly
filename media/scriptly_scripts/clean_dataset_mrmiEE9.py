import pandas as pd
import sys

def clean_dataset(input_file, output_file):
    df = pd.read_csv(input_file)
    df_cleaned = df.dropna()
    df_cleaned.to_csv(output_file, index=False)
    print(f"Cleaned dataset saved to {output_file}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python clean_dataset.py <input_file> <output_file>")
        sys.exit(1)
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    clean_dataset(input_file, output_file)