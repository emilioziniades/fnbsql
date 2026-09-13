# fnbsql

`fnbsql` extracts transactions from FNB PDF statements and saves them into a SQLite database.
The database file is stored at `$XDG_DATA_HOME/fnbsql/fnbsql.sqlite`.
You can choose a different location with `--database`.
All amounts are stored as integer cents.

```sh
uvx --from git+https://github.com/emilioziniades/fnbsql.git fnbsql -f statement.pdf
sqlite3 ~/.local/share/fnbsql/fnbsql.sqlite \
  'SELECT date, amount AS amount_cents, description FROM transactions ORDER BY date;'
```
