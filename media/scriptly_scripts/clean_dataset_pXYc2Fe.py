import pandas as pd
import argparse
import os

def clean_dataset(input_file):
    df = pd.read_csv(input_file)
    df_cleaned = df.dropna()

    output_dir = os.getenv("SCRIPTLY_OUTPUT_DIR", "output")
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "cleaned_dataset.csv")

    df_cleaned.to_csv(output_file, index=False)
    print(f"✅ Cleaned dataset saved to {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean a dataset by removing missing values.")
    parser.add_argument(
        "input_file",
        type=argparse.FileType('r'),                  # ✅ Specify FileType here
        help="Path to the input CSV file"
    )
    args = parser.parse_args()

    clean_dataset(args.input_file.name)               # ✅ Use .name because FileType returns an open file object
