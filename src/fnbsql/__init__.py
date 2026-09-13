import logging
from argparse import ArgumentParser
from pathlib import Path

from fnbsql.database import Database
from fnbsql.pdf_statement import PdfStatement

DEFAULT_DATABASE = Path(__file__).resolve().parents[2] / "fnbsql.sqlite"


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("-f", "--file", action="append", type=Path, required=True)
    parser.add_argument("-d", "--database", type=Path, default=DEFAULT_DATABASE)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    with Database(args.database) as database:
        for file in args.file:
            statement = PdfStatement(file)
            database.insert(statement.statement)
