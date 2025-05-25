import os
import pandas as pd

def main(input_file):
    # Read the CSV input
    df = pd.read_csv(input_file)

    # Multiply 'value' column by 10 and add a new column
    if 'value' not in df.columns:
        raise ValueError("Column 'value' not found in input file.")

    df['value_times_10'] = df['value'] * 10

    # Get output directory from environment or default
    output_dir = os.getenv("SCRIPTLY_OUTPUT_DIR", "output")
    os.makedirs(output_dir, exist_ok=True)

    # Save the modified file
    output_path = os.path.join(output_dir, "calculated_dataset.csv")
    df.to_csv(output_path, index=False)

    print(f"✅ Calculated dataset saved to {output_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Multiply 'value' column by 10.")
    parser.add_argument("--input_file", required=True, help="Path to the input CSV file.")
    args = parser.parse_args()

    main(args.input_file)
