from werkzeug.security import generate_password_hash
import sqlite3

conn = sqlite3.connect(r'C:\ALIDEEA\gestiune.db')
parola_noua = generate_password_hash('cristi@1')
conn.execute("UPDATE utilizatori SET parola=? WHERE username='cristi'", (parola_noua,))
conn.commit()

row = conn.execute("SELECT username, rol FROM utilizatori WHERE username='cristi'").fetchone()
if row:
    print(f'Parola setata pentru: {row[0]} (rol: {row[1]})')
else:
    print('Utilizatorul cristi nu exista!')
conn.close()
