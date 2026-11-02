import os
import sqlite3
import pickle

# 1. COMMAND INJECTION (Critical)
def ping_server(ip_address):
    """
    DIKKAT KYA HAI: 
    Yahan user ka input 'ip_address' seedhe operating system ke shell me pass ho raha hai.
    
    ATTACK KAISE HOGA:
    Agar user ip_address ki jagah "127.0.0.1; cat /etc/passwd" ya "127.0.0.1; rm -rf /" daal de,
    toh ping hone ke baad semicolon (;) ke aage wali command OS par run ho jayegi aur server hack ho jayega.
    """
    # Vulnerable line
    os.system("ping -c 1 " + ip_address)


# 2. SQL INJECTION (High)
def login_user(username, password):
    """
    DIKKAT KYA HAI: 
    User ka input seedhe SQL query ke andar plus (+) lagakar (string concatenation) joda ja raha hai.
    
    ATTACK KAISE HOGA:
    Agar attacker username me "admin' --" daal de, toh query banegi: 
    SELECT * FROM users WHERE username = 'admin' --' AND password = '...'
    SQL me '--' ka matlab comment hota hai. Toh password check ignore ho jayega aur attacker login kar lega.
    """
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # Vulnerable line
    query = "SELECT * FROM users WHERE username = '" + username + "' AND password = '" + password + "'"
    cursor.execute(query)
    return cursor.fetchall()


# 3. PATH TRAVERSAL / DIRECTORY TRAVERSAL (High)
def read_user_file(filename):
    """
    DIKKAT KYA HAI: 
    User dwara bheja gaya 'filename' bina kisi validation ke file path me append ho raha hai.
    
    ATTACK KAISE HOGA:
    Attacker filename ki jagah "../../../../etc/passwd" bhej sakta hai. 
    "../" ka matlab folder se bahar aana hota hai. Isse wo server ki main directory tak jaakar secret files read kar lega.
    """
    base_directory = "/var/www/uploads/"
    
    # Vulnerable line
    file_path = base_directory + filename
    with open(file_path, 'r') as file:
        return file.read()


# 4. UNSAFE DESERIALIZATION (High)
def load_session_data(serialized_cookie):
    """
    DIKKAT KYA HAI: 
    Python ka 'pickle' module untrusted data par use kiya ja raha hai. Pickle sirf variables ko nahi,
    balki functions aur executable code ko bhi store aur load kar sakta hai.
    
    ATTACK KAISE HOGA:
    Attacker ek malicious pickle object banayega jisme aisi command hogi jo load hote hi execute ho jayegi.
    Jaise hi server `pickle.loads()` chalayega, attacker ka code server par run ho jayega.
    """
    # Vulnerable line
    return pickle.loads(serialized_cookie)


# 5. HARDCODED SECRET (Medium)
def process_payment():
    """
    DIKKAT KYA HAI: 
    Payment gateway ki secret API key seedhe source code (plain text) me likhi hui hai.
    
    ATTACK KAISE HOGA:
    Agar ye code galti se GitHub par public ho gaya, ya kisi employee ne code leak kar diya, 
    toh koi bhi is API key ka use karke company ke account se paise nikal sakta hai ya fake payments kar sakta hai.
    Secrets hamesha .env file (environment variables) me hone chahiye.
    """
    # Vulnerable line
    STRIPE_SECRET_KEY = "sk_live_51Hxxxxx_MY_SUPER_SECRET_KEY_12345"
    
    # Process payment logic here...
    return "Payment successful using key: " + STRIPE_SECRET_KEY