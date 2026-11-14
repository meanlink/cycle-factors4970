from sqlalchemy import inspect, text
from src.config.database import Base, engine
from src import models


# Columns added after the first release. ``create_all`` only creates missing
# tables, so existing installations need these additive migrations.
_ADDITIVE_COLUMNS = {
    'datasets': {
        'observation_date': "VARCHAR(10) DEFAULT '' NOT NULL",
    },
    'jobs': {
        'combination_id': 'INTEGER',
        'combination_name': 'VARCHAR(160)',
        'combination_version_id': 'INTEGER',
        'combination_version_no': 'INTEGER',
        'sample_checksum': 'VARCHAR(64)',
        'samples': 'JSON',
    },
    'reports': {
        'job_name': "VARCHAR(160) DEFAULT '' NOT NULL",
        'combination_id': 'INTEGER',
        'combination_name': 'VARCHAR(160)',
        'combination_version_no': 'INTEGER',
        'sample_checksum': 'VARCHAR(64)',
    },
    'deliveries': {
        'job_id': 'INTEGER',
        'job_name': "VARCHAR(160) DEFAULT '' NOT NULL",
        'combination_id': 'INTEGER',
        'combination_name': 'VARCHAR(160)',
        'combination_version_no': 'INTEGER',
        'sample_checksum': 'VARCHAR(64)',
    },
}


def _add_missing_columns():
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table, columns in _ADDITIVE_COLUMNS.items():
            if table not in existing_tables:
                continue
            present = {column['name'] for column in inspector.get_columns(table)}
            for name, definition in columns.items():
                if name in present:
                    continue
                connection.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {definition}'))
        # Combination jobs do not reference a single dataset. PostgreSQL keeps
        # the old NOT NULL constraint when adding the nullable column above.
        if engine.dialect.name == 'postgresql' and 'jobs' in existing_tables:
            connection.execute(text('ALTER TABLE jobs ALTER COLUMN dataset_id DROP NOT NULL'))


def migrate():
    Base.metadata.create_all(engine)
    _add_missing_columns()


if __name__ == '__main__':
    migrate()
