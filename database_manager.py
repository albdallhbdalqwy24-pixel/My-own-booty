import sqlite3
import time
import os
from datetime import datetime, timedelta

DB_PATH = 'accounts.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # جدول المستخدمين والاشتراكات
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            join_date REAL,
            expiry_date REAL,
            is_lifetime BOOLEAN DEFAULT 0,
            status TEXT DEFAULT 'pending',
            total_email_reports INTEGER DEFAULT 0,
            total_telegram_reports INTEGER DEFAULT 0,
            external_emails_count INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

class DatabaseManager:
    def __init__(self):
        init_db()

    def get_connection(self):
        conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
        return conn

    def add_user(self, user_id, username, days=0, is_lifetime=False):
        conn = self.get_connection()
        c = conn.cursor()
        
        now = time.time()
        if is_lifetime:
            expiry = 9999999999.0
        else:
            expiry = now + (days * 24 * 3600)
            
        c.execute('''
            INSERT OR REPLACE INTO users 
            (user_id, username, join_date, expiry_date, is_lifetime, status)
            VALUES (?, ?, ?, ?, ?, 'active')
        ''', (user_id, username, now, expiry, 1 if is_lifetime else 0))
        
        conn.commit()
        conn.close()
        return expiry

    def get_user(self, user_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = c.fetchone()
        conn.close()
        return user

    def check_subscription(self, user_id):
        user = self.get_user(user_id)
        if not user:
            return "not_found"
        
        # user structure: 0:id, 1:username, 2:join, 3:expiry, 4:lifetime, 5:status
        status = user[5]
        expiry = user[3]
        
        if status != 'active':
            return "inactive"
            
        if time.time() > expiry:
            return "expired"
            
        return "active"

    def get_all_users(self):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('SELECT * FROM users')
        users = c.fetchall()
        conn.close()
        return users

    def remove_user(self, user_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()

    def update_user_status(self, user_id, status):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('UPDATE users SET status = ? WHERE user_id = ?', (status, user_id))
        conn.commit()
        conn.close()

    def update_stats(self, user_id, telegram_reports=0, email_reports=0):
        conn = self.get_connection()
        c = conn.cursor()
        if telegram_reports > 0:
            c.execute('UPDATE users SET total_telegram_reports = total_telegram_reports + ? WHERE user_id = ?', (telegram_reports, user_id))
        if email_reports > 0:
            c.execute('UPDATE users SET total_email_reports = total_email_reports + ? WHERE user_id = ?', (email_reports, user_id))
        conn.commit()
        conn.close()

    def get_all_accounts(self):
        """جلب كافة حسابات تلجرام من قاعدة البيانات"""
        conn = self.get_connection()
        c = conn.cursor()
        try:
            # جلب كافة الحسابات النشطة
            c.execute('''
                SELECT id, username, phone, session, is_active, owner_id 
                FROM accounts 
                WHERE is_active = 1
            ''')
            rows = c.fetchall()
            accounts = []
            for row in rows:
                accounts.append({
                    "id": row[0],
                    "username": row[1],
                    "phone": row[2],
                    "session": row[3],
                    "is_active": row[4],
                    "owner_id": row[5]
                })
            return accounts
        except Exception as e:
            print(f"Error fetching all accounts: {e}")
            return []
        finally:
            conn.close()

db = DatabaseManager()
