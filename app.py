"""
Pay and Parking Management System
Flask Backend - app.py
"""

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime, timedelta
import json
import os
import hashlib

app = Flask(__name__)
app.secret_key = 'parking_secret_key_2024'

# ─────────────────────────────────────────
# IN-MEMORY DATABASE (no external DB needed)
# ─────────────────────────────────────────

users = {}          # { email: { name, email, password_hash } }
bookings = []       # list of booking dicts
next_booking_id = 1

# 20 parking slots: A1-A5, B1-B5, C1-C5, D1-D5
def init_slots():
    slots = {}
    for row in ['A', 'B', 'C', 'D']:
        for num in range(1, 6):
            slot_id = f"{row}{num}"
            slots[slot_id] = {
                'id': slot_id,
                'row': row,
                'number': num,
                'status': 'available',  # available / occupied
                'vehicle': None,
                'booked_by': None,
                'booking_id': None,
            }
    return slots

parking_slots = init_slots()

# Rates (₹ per hour)
RATES = {
    '2W': 20,   # Two-Wheeler
    '4W': 50,   # Four-Wheeler / Car
    'HV': 100,  # Heavy Vehicle
}

# ─────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_current_user():
    if 'user_email' in session:
        return users.get(session['user_email'])
    return None

def release_expired_slots():
    """Auto-release slots whose booking time has expired."""
    now = datetime.now()
    for booking in bookings:
        if booking['status'] == 'active':
            end_time = datetime.strptime(booking['end_time'], '%Y-%m-%d %H:%M')
            if now > end_time:
                booking['status'] = 'completed'
                slot = parking_slots.get(booking['slot_id'])
                if slot:
                    slot['status'] = 'available'
                    slot['vehicle'] = None
                    slot['booked_by'] = None
                    slot['booking_id'] = None

def get_admin_stats():
    total_earnings = sum(b['amount'] for b in bookings if b['status'] in ['active', 'completed'])
    total_bookings = len(bookings)
    active_bookings = sum(1 for b in bookings if b['status'] == 'active')
    available_slots = sum(1 for s in parking_slots.values() if s['status'] == 'available')
    return {
        'total_earnings': total_earnings,
        'total_bookings': total_bookings,
        'active_bookings': active_bookings,
        'available_slots': available_slots,
    }

# ─────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────

# 1. HOME
@app.route('/')
def home():
    release_expired_slots()
    available = sum(1 for s in parking_slots.values() if s['status'] == 'available')
    occupied = sum(1 for s in parking_slots.values() if s['status'] == 'occupied')
    return render_template('home.html', available=available, occupied=occupied, user=get_current_user())

# 2. REGISTER
@app.route('/register', methods=['GET', 'POST'])
def register():
    if get_current_user():
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        phone = request.form.get('phone', '').strip()

        # Validations
        if not all([name, email, password, confirm, phone]):
            flash('All fields are required.', 'error')
            return render_template('register.html')
        if email in users:
            flash('Email already registered. Please login.', 'error')
            return render_template('register.html')
        if password != confirm:
            flash('Passwords do not match.', 'error')
            return render_template('register.html')
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('register.html')

        users[email] = {
            'name': name,
            'email': email,
            'password_hash': hash_password(password),
            'phone': phone,
            'joined': datetime.now().strftime('%d %b %Y'),
        }
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html', user=None)

# 3. LOGIN
@app.route('/login', methods=['GET', 'POST'])
def login():
    if get_current_user():
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        # Admin login
        if email == 'admin@parking.com' and password == 'admin123':
            session['user_email'] = email
            session['is_admin'] = True
            if email not in users:
                users[email] = {'name': 'Administrator', 'email': email, 'phone': '0000000000', 'joined': 'System', 'password_hash': hash_password(password)}
            flash('Welcome, Admin!', 'success')
            return redirect(url_for('admin'))

        user = users.get(email)
        if user and user['password_hash'] == hash_password(password):
            session['user_email'] = email
            session['is_admin'] = False
            flash(f'Welcome back, {user["name"]}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'error')

    return render_template('login.html', user=None)

# 4. LOGOUT
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('home'))

# 5. DASHBOARD
@app.route('/dashboard')
def dashboard():
    user = get_current_user()
    if not user:
        flash('Please login to access the dashboard.', 'error')
        return redirect(url_for('login'))

    release_expired_slots()
    user_bookings = [b for b in bookings if b['user_email'] == user['email']]
    active = [b for b in user_bookings if b['status'] == 'active']
    history = [b for b in user_bookings if b['status'] != 'active']
    total_spent = sum(b['amount'] for b in user_bookings)

    return render_template('dashboard.html', user=user,
                           active_bookings=active,
                           history=history,
                           total_spent=total_spent)

# 6. PARKING SLOTS
@app.route('/slots')
def slots():
    user = get_current_user()
    release_expired_slots()
    rows = {}
    for slot in parking_slots.values():
        rows.setdefault(slot['row'], []).append(slot)
    for row in rows:
        rows[row].sort(key=lambda x: x['number'])
    available_count = sum(1 for s in parking_slots.values() if s['status'] == 'available')
    occupied_count = sum(1 for s in parking_slots.values() if s['status'] == 'occupied')
    return render_template('slots.html', user=user, rows=rows,
                           available_count=available_count, occupied_count=occupied_count)

# 7. BOOKING
@app.route('/book', methods=['GET', 'POST'])
def book():
    user = get_current_user()
    if not user:
        flash('Please login to book a slot.', 'error')
        return redirect(url_for('login'))

    release_expired_slots()
    available_slots = [s for s in parking_slots.values() if s['status'] == 'available']

    if request.method == 'POST':
        slot_id = request.form.get('slot_id')
        vehicle_type = request.form.get('vehicle_type')
        vehicle_number = request.form.get('vehicle_number', '').strip().upper()
        duration = request.form.get('duration')

        # Validation
        if not all([slot_id, vehicle_type, vehicle_number, duration]):
            flash('All fields are required.', 'error')
            return render_template('book.html', user=user, slots=available_slots, rates=RATES)

        slot = parking_slots.get(slot_id)
        if not slot or slot['status'] == 'occupied':
            flash('Selected slot is no longer available.', 'error')
            return render_template('book.html', user=user, slots=available_slots, rates=RATES)

        try:
            duration_hrs = float(duration)
            if duration_hrs <= 0 or duration_hrs > 24:
                raise ValueError
        except ValueError:
            flash('Invalid duration. Must be between 0.5 and 24 hours.', 'error')
            return render_template('book.html', user=user, slots=available_slots, rates=RATES)

        rate = RATES.get(vehicle_type, 50)
        amount = round(rate * duration_hrs)
        start_time = datetime.now()
        end_time = start_time + timedelta(hours=duration_hrs)

        # Store booking in session for payment confirmation
        session['pending_booking'] = {
            'slot_id': slot_id,
            'vehicle_type': vehicle_type,
            'vehicle_number': vehicle_number,
            'duration': duration_hrs,
            'amount': amount,
            'start_time': start_time.strftime('%Y-%m-%d %H:%M'),
            'end_time': end_time.strftime('%Y-%m-%d %H:%M'),
            'rate': rate,
        }
        return redirect(url_for('payment'))

    return render_template('book.html', user=user, slots=available_slots, rates=RATES)

# 8. PAYMENT
@app.route('/payment', methods=['GET', 'POST'])
def payment():
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    pending = session.get('pending_booking')
    if not pending:
        flash('No booking in progress.', 'error')
        return redirect(url_for('book'))

    if request.method == 'POST':
        global next_booking_id
        # Confirm booking
        slot = parking_slots.get(pending['slot_id'])
        if not slot or slot['status'] == 'occupied':
            flash('Slot became unavailable. Please book again.', 'error')
            session.pop('pending_booking', None)
            return redirect(url_for('book'))

        booking = {
            'id': next_booking_id,
            'user_email': user['email'],
            'user_name': user['name'],
            'slot_id': pending['slot_id'],
            'vehicle_type': pending['vehicle_type'],
            'vehicle_number': pending['vehicle_number'],
            'duration': pending['duration'],
            'amount': pending['amount'],
            'start_time': pending['start_time'],
            'end_time': pending['end_time'],
            'status': 'active',
            'booked_on': datetime.now().strftime('%d %b %Y %H:%M'),
        }
        bookings.append(booking)
        next_booking_id += 1

        # Mark slot occupied
        slot['status'] = 'occupied'
        slot['vehicle'] = pending['vehicle_number']
        slot['booked_by'] = user['name']
        slot['booking_id'] = booking['id']

        session.pop('pending_booking', None)
        flash(f'Booking confirmed! Slot {pending["slot_id"]} is yours until {pending["end_time"]}.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('payment.html', user=user, booking=pending)

# 9. ADMIN PANEL
@app.route('/admin')
def admin():
    if not session.get('is_admin'):
        flash('Admin access required.', 'error')
        return redirect(url_for('login'))

    release_expired_slots()
    stats = get_admin_stats()
    all_bookings = sorted(bookings, key=lambda x: x['id'], reverse=True)
    return render_template('admin.html', user=get_current_user(),
                           stats=stats, bookings=all_bookings,
                           slots=parking_slots, users=users)

@app.route('/admin/add_slot', methods=['POST'])
def admin_add_slot():
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    slot_id = request.form.get('slot_id', '').upper().strip()
    if slot_id and slot_id not in parking_slots:
        parking_slots[slot_id] = {
            'id': slot_id,
            'row': slot_id[0] if slot_id else 'X',
            'number': int(slot_id[1:]) if slot_id[1:].isdigit() else 0,
            'status': 'available',
            'vehicle': None,
            'booked_by': None,
            'booking_id': None,
        }
        flash(f'Slot {slot_id} added successfully.', 'success')
    else:
        flash('Invalid or duplicate slot ID.', 'error')
    return redirect(url_for('admin'))

@app.route('/admin/remove_slot/<slot_id>')
def admin_remove_slot(slot_id):
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    slot = parking_slots.get(slot_id)
    if slot and slot['status'] == 'available':
        del parking_slots[slot_id]
        flash(f'Slot {slot_id} removed.', 'success')
    else:
        flash('Cannot remove occupied slot.', 'error')
    return redirect(url_for('admin'))

# 10. API ENDPOINT
@app.route('/api/slots')
def api_slots():
    release_expired_slots()
    data = []
    for s in parking_slots.values():
        data.append({
            'id': s['id'],
            'status': s['status'],
            'vehicle': s['vehicle'],
            'booked_by': s['booked_by'],
        })
    return jsonify({
        'slots': data,
        'available': sum(1 for s in data if s['status'] == 'available'),
        'occupied': sum(1 for s in data if s['status'] == 'occupied'),
        'total': len(data),
    })

# 11. 404 ERROR PAGE
@app.errorhandler(404)
def not_found(e):
    return render_template('404.html', user=get_current_user()), 404

# ─────────────────────────────────────────
if __name__ == '__main__':
    # Add a demo user
    users['demo@parking.com'] = {
        'name': 'Demo User',
        'email': 'demo@parking.com',
        'password_hash': hash_password('demo123'),
        'phone': '9876543210',
        'joined': '01 Jan 2024',
    }
    app.run(debug=True)
