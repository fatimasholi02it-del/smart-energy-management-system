from sqlalchemy import text
from database import engine


def main():

    with engine.begin() as conn:

        conn.execute(
            text(
                """
                ALTER TABLE energy_readings
                ADD COLUMN IF NOT EXISTS power_kw DOUBLE PRECISION;
                """
            )
        )

        conn.execute(
            text(
                """
                ALTER TABLE energy_readings
                ADD COLUMN IF NOT EXISTS energy_kwh DOUBLE PRECISION;
                """
            )
        )

    print("Columns added successfully")

    with engine.connect() as conn:

        result = conn.execute(
            text(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'energy_readings'
                ORDER BY ordinal_position;
                """
            )
        )

        print("\nenergy_readings columns:")

        for row in result:
            print(row)


if __name__ == "__main__":
    main()