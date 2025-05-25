import argparse
import os
import pandas as pd

def main():
    parser = argparse.ArgumentParser(description="Multiply 'value' column by 10")
    parser.add_argument("--input_file", type=argparse.FileType("r"), help="Path to input CSV", required=True)

    args = parser.parse_args()
    input_path = args.input_file.name

    # Load the CSV
    df = pd.read_csv(input_path)

    # Multiply only the 'value' column
    if 'value' in df.columns:
        df['value'] = pd.to_numeric(df['value'], errors='coerce') * 10
    else:
        print("⚠️ 'value' column not found.")
        return

    # Output directory logic
    output_dir = os.getenv("SCRIPTLY_OUTPUT_DIR", "output")
    os.makedirs(output_dir, exist_ok=True)

    output_path = os.path.join(output_dir, "modified.csv")
    df.to_csv(output_path, index=False)

    print(f"Modified dataset saved to {output_path}")

if __name__ == "__main__":
    main()
