import pandas as pd
import argparse
import os


def clean_dataset(input_path):
    # Load the dataset
    df = pd.read_csv(input_path)

    # Drop rows with missing values
    df_cleaned = df.dropna()

    # Output directory from environment or default to 'output'
    output_dir = os.getenv("SCRIPTLY_OUTPUT_DIR", "output")
    os.makedirs(output_dir, exist_ok=True)

    # Output file path
    output_file = os.path.join(output_dir, "cleaned_dataset.csv")
    df_cleaned.to_csv(output_file, index=False)

    print(f"✅ Cleaned dataset saved to {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean a dataset by removing missing values.")

    # Use optional-style argument, required by Scriptly/Wooey
    parser.add_argument(
        "--input_file",
        required=True,
        help="Path to the input CSV file"
    )

    args = parser.parse_args()
    clean_dataset(args.input_file)
