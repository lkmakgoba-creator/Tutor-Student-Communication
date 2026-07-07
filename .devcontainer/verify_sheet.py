import os
os.chdir(r'c:\Users\lkmak\OneDrive\Desktop\Lesetja_PA\Tutor-Student-Communication')
import app

df = app.load_data()
print(df.head(2).to_string())
print('ROWS', len(df))
