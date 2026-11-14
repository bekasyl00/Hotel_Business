#!/usr/bin/env python3
"""Non-destructive LOCAL PostgreSQL restore rehearsal. Source is never modified."""
import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid
import psycopg
from psycopg import sql


def main():
    if os.environ.get('PGHOST') not in ('127.0.0.1', 'localhost', '::1'):
        raise RuntimeError('Local PGHOST required; production restore is a separate controlled operation')
    source = os.environ.get('PGDATABASE')
    if not source:
        raise RuntimeError('PGDATABASE required')
    folder = Path(tempfile.mkdtemp(prefix='tynys-restore-'))
    folder.chmod(0o700)
    backup = folder / 'database.dump'
    target = 'tynys_restore_' + uuid.uuid4().hex[:12]
    env = os.environ.copy()
    def run(args):
        result = subprocess.run(args, env=env, capture_output=True)
        if result.returncode:
            # Database errors can contain personal data, never echo subprocess output.
            raise RuntimeError(f'{Path(args[0]).name} failed; diagnostic withheld; no database was deleted')
    def inventory(database):
        with psycopg.connect(dbname=database) as connection:
            tables = connection.execute("SELECT schemaname,tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2").fetchall()
            result = {}
            for schema, table in tables:
                digest, count = hashlib.sha256(), 0
                query = sql.SQL('SELECT to_jsonb(t)::text FROM {}.{} AS t ORDER BY 1').format(
                    sql.Identifier(schema), sql.Identifier(table))
                with connection.cursor(name='restore_inventory') as cursor:
                    cursor.execute(query)
                    for (value,) in cursor:
                        digest.update(value.encode('utf-8') + b'\n')
                        count += 1
                result[f'{schema}.{table}'] = {'rows': count, 'digest': digest.hexdigest()}
            return result
    before = inventory(source)
    if not before:
        raise RuntimeError('Source has no application tables; empty backup is not acceptance')
    for tool in ('pg_dump', 'pg_restore', 'createdb'):
        if not shutil.which(tool):
            raise RuntimeError(f'{tool} not found in PATH')
    run(['pg_dump','--format=custom','--file',str(backup)])
    backup.chmod(0o600)
    run(['createdb',target])
    run(['pg_restore','--exit-on-error','--no-owner','--no-acl','--dbname',target,str(backup)])
    after = inventory(target)
    if before != after:
        raise RuntimeError('Restored table contents differ; freeze source writes during rehearsal')
    (folder/'result.json').write_text(json.dumps({'source':source,'restored':target,'tables':len(after),'rows':sum(table['rows'] for table in after.values()),'contentsMatch':True},indent=2))
    print(f"Restore passed: {len(after)} tables, {sum(table['rows'] for table in after.values())} rows, content hashes match. Evidence: {folder}/result.json")
    print('Source untouched. Restored database retained. Content hashes do not prove file/key recovery, runtime grants or production RPO/RTO.')

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Do not print arbitrary driver exceptions or their connection strings.
        print(str(error) if isinstance(error, RuntimeError) else 'Restore rehearsal failed; driver detail withheld.')
        raise SystemExit(1)
