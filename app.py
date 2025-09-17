from flask import Flask, render_template, request, jsonify, redirect, url_for
from datetime import datetime, date
import json
import os

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

# Simple file-based database
DATABASE_FILE = 'event_data.json'

def load_db():
    """Load database from file"""
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, 'r') as f:
            return json.load(f)
    else:
        # Initialize default structure
        return {
            'rsvps': {},
            'seats': {f"table_{i}": [None] * 10 for i in range(1, 11)}
        }

def save_db(data):
    """Save database to file"""
    with open(DATABASE_FILE, 'w') as f:
        json.dump(data, f, indent=2)

# Deadline for seat changes
SEAT_CHANGE_DEADLINE = date(2025, 10, 1)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/rsvp', methods=['GET', 'POST'])
def rsvp():
    if request.method == 'POST':
        # Get form data
        attending = request.form.get('attending')
        
        # If not attending, show thank you message
        if attending == 'no':
            return render_template('thank_you.html', attending=False)
        
        # Extract form data for attending guests
        full_name = request.form.get('full_name')
        surname = request.form.get('surname')
        email = request.form.get('email')
        cellphone = request.form.get('cellphone')
        bringing_guest = request.form.get('bringing_guest')
        guest_list = request.form.get('guest_list', '')
        dietary_requirements = request.form.get('dietary_requirements')
        food_allergies = request.form.get('food_allergies', '')
        
        # Validate required fields
        if not all([full_name, surname, email, cellphone, dietary_requirements]):
            return render_template('rsvp_form.html', error="Please fill in all required fields")
        
        # Store RSVP data
        rsvp_data = {
            'full_name': full_name,
            'surname': surname,
            'email': email,
            'cellphone': cellphone,
            'bringing_guest': bringing_guest,
            'guest_list': guest_list.strip() if guest_list else '',
            'dietary_requirements': dietary_requirements,
            'food_allergies': food_allergies,
            'submitted_at': datetime.now().isoformat()
        }
        
        # Update database
        data = load_db()
        data['rsvps'][email] = rsvp_data
        save_db(data)
        
        # Redirect to seating chart
        return redirect(url_for('seating_chart', email=email))
    
    return render_template('rsvp_form.html')

@app.route('/seating-chart')
def seating_chart():
    email = request.args.get('email')
    data = load_db()
    
    if not email or email not in data['rsvps']:
        return redirect(url_for('index'))
    
    # Check if deadline has passed
    today = date.today()
    deadline_passed = today > SEAT_CHANGE_DEADLINE
    
    # Get current seating arrangement
    data = load_db()
    seats = data['seats']
    rsvp_data = data['rsvps'][email]
    
    return render_template('seating_chart.html', 
                         seats=seats, 
                         email=email, 
                         rsvp_data=rsvp_data,
                         deadline_passed=deadline_passed,
                         deadline=SEAT_CHANGE_DEADLINE.strftime('%B %d, %Y'))

@app.route('/api/seat-info')
def seat_info():
    table = request.args.get('table')
    try:
        seat_index = int(request.args.get('seat', 0))
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid seat number'}), 400
    
    data = load_db()
    seats = data['seats']
    if table in seats and 0 <= seat_index < len(seats[table]):
        occupant = seats[table][seat_index]
        if occupant:
            return jsonify({
                'occupied': True,
                'occupant': f"{occupant['full_name']} {occupant['surname']}"
            })
        else:
            return jsonify({'occupied': False})
    
    return jsonify({'error': 'Invalid seat'}), 400

@app.route('/api/select-seat', methods=['POST'])
def select_seat():
    data = request.json or {}
    email = data.get('email')
    table = data.get('table')
    
    try:
        seat_index = int(data.get('seat', 0))
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid seat number'}), 400
    
    # Validate table and seat range
    if not table or not table.startswith('table_'):
        return jsonify({'error': 'Invalid table'}), 400
    
    if not 0 <= seat_index < 10:
        return jsonify({'error': 'Invalid seat number'}), 400
    
    # Check if deadline has passed
    today = date.today()
    if today > SEAT_CHANGE_DEADLINE:
        return jsonify({'error': 'Seat selection deadline has passed'}), 400
    
    # Load data
    data = load_db()
    
    # Validate user
    if email not in data['rsvps']:
        return jsonify({'error': 'Invalid user'}), 400
    
    seats = data['seats']
    rsvp_data = data['rsvps'][email]
    
    # Remove user from any previous seat
    for t in seats:
        for i, occupant in enumerate(seats[t]):
            if occupant and occupant.get('email') == email:
                seats[t][i] = None
    
    # Check if requested seat is available
    if table in seats and 0 <= seat_index < len(seats[table]):
        if seats[table][seat_index] is None:
            # Assign seat
            seats[table][seat_index] = {
                'email': email,
                'full_name': rsvp_data['full_name'],
                'surname': rsvp_data['surname']
            }
            data['seats'] = seats
            save_db(data)
            
            table_name = table.replace("_", " ").title() if table else "Unknown Table"
            return jsonify({
                'success': True, 
                'message': f'Seat assigned at {table_name} - Seat {seat_index + 1}'
            })
        else:
            return jsonify({'error': 'Seat is already taken'}), 400
    
    return jsonify({'error': 'Invalid seat'}), 400

@app.route('/success')
def success():
    email = request.args.get('email')
    data = load_db()
    
    if not email or email not in data['rsvps']:
        return redirect(url_for('index'))
    
    rsvp_data = data['rsvps'][email]
    
    # Find user's seat
    seats = data['seats']
    user_seat = None
    for table_name, table_seats in seats.items():
        for i, occupant in enumerate(table_seats):
            if occupant and occupant.get('email') == email:
                user_seat = {
                    'table': table_name.replace('_', ' ').title(),
                    'seat': i + 1
                }
                break
    
    return render_template('success.html', rsvp_data=rsvp_data, user_seat=user_seat)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)