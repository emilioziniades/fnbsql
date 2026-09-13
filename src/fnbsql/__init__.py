from argparse import ArgumentParser
from pprint import pprint

import pdfplumber


def main():
    parser = ArgumentParser()
    parser.add_argument("-f", "--file", action="append", required=True)
    args = parser.parse_args()

    files = args.file

    print(args.file)
    for file in files:
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                table = page.extract_tables(
                    {
                        "vertical_strategy": "lines",
                        "horizontal_strategy": "text",
                        "min_words_horizontal": 6,
                        "snap_x_tolerance": 4,
                        "snap_y_tolerance": 4,
                    }
                )
                pprint(table)
                breakpoint()
                break
