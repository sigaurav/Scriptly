import pandas as pd
import argparse

def clean_dataset(input_file, output_file):
    df = pd.read_csv(input_file)
    df_cleaned = df.dropna()
    df_cleaned.to_csv(output_file, index=False)
    print(f"Cleaned dataset saved to {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean a dataset by removing missing values.")
    parser.add_argument("input_file", help="Path to the input CSV file")
    parser.add_argument("output_file", help="Path to the output CSV file")
    args = parser.parse_args()

    clean_dataset(args.input_file, args.output_file)