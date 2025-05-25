import os
import pandas as pd
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file", type=argparse.FileType("r"), help="Input CSV file")
    args = parser.parse_args()

    df = pd.read_csv(args.input_file)
    df['value_x10'] = df['value'] * 10

    output_dir = os.getenv("SCRIPTLY_OUTPUT_DIR", "output")
    os.makedirs(output_dir, exist_ok=True)

    output_path = os.path.join(output_dir, "value_multiplied.csv")
    df.to_csv(output_path, index=False)
    print(f"✅ File saved to {output_path}")

if __name__ == "__main__":
    main()
