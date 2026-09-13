# fnbsql

A small Python CLI tool to extract transactions from FNB PDF statements and save them into a SQLite database.

The database file is stored at `$XDG_DATA_HOME/fnbsql/fnbsql.sqlite`.
You can choose a different location with `--database`.
Specify one or more files with the `-f` or `--file` options.

You can install it using `uv`.
```sh
uv tool install git+https://github.com/emilioziniades/fnbsql.git
fnbsql -f statement.pdf
```

Or run the CLI remotely using `uvx`.
```
uvx --from git+https://github.com/emilioziniades/fnbsql.git fnbsql -f statement.pdf
```

Now you have a sqlite database which you can query directly or consume from another application.

```sh
sqlite3 ~/.local/share/fnbsql/fnbsql.sqlite \
  'SELECT date, amount AS amount_cents, description FROM transactions ORDER BY date;'
```
