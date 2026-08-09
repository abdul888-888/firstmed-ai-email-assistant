import psycopg2

try:
    conn = psycopg2.connect('postgresql://postgres:vFrIaHpddKszeEbQBiPygipvKBXLEJFw@postgres.railway.internal:5432/railway')
    cur = conn.cursor()
    
    # Insert the missing migration versions
    cur.execute("INSERT INTO alembic_version (version_num, is_primary) VALUES ('0013', true), ('0014', true) ON CONFLICT (version_num) DO NOTHING;")
    conn.commit()
    
    print('✅ Success! Migrations 0013 and 0014 marked as complete in Railway database.')
    
    cur.close()
    conn.close()
except Exception as e:
    print(f'❌ Error: {e}')
