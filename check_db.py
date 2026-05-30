import pymysql
import config

try:
    connection = pymysql.connect(
        host=config.MYSQL_HOST,
        user=config.MYSQL_USER,
        password=config.MYSQL_PASSWORD,
        database=config.MYSQL_DB,
        cursorclass=pymysql.cursors.DictCursor,
    )
    with connection.cursor() as cursor:
        cursor.execute("DESCRIBE threads")
        columns = cursor.fetchall()
        print("Columns in 'threads' table:")
        for col in columns:
            print(f"- {col['Field']}")
    connection.close()
except Exception as e:
    print(f"Error: {e}")
